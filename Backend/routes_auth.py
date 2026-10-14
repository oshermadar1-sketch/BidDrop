# routes_auth.py
# FastAPI routes for wallet-based login:
# 1) POST /auth/nonce  -> issue short-lived challenge and save to DB
# 2) POST /auth/verify -> verify signature, upsert user, return JWT

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
import os, secrets, binascii

from .Database.db import get_db

from substrateinterface.utils.ss58 import ss58_decode, ss58_encode

SS58_PREFIX = 42  


def normalize_address(address: str) -> str:
    """
    Decode any valid SS58 and re-encode with our canonical prefix.
    Always store & return this canonical form.
    """
    pubkey_hex = ss58_decode(address)      # hex (no 0x)
    pubkey = bytes.fromhex(pubkey_hex)     # 32 bytes
    return ss58_encode(pubkey, SS58_PREFIX)


# --- JWT (HS256) ---
from jose import jwt
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PROD")
JWT_ALG = "HS256"
# Login lifetime in minutes (12 hours, so a demo session does not expire mid-way)
JWT_TTL_MIN = int(os.getenv("JWT_TTL_MIN", "720"))

def create_access_token(subject: str) -> str:
    """Create a short-lived JWT. 'subject' is the wallet address."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_TTL_MIN)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

# --- Signature verification using substrate-interface ---
#   pip install substrate-interface
from substrateinterface import Keypair, KeypairType
from substrateinterface.utils.ss58 import ss58_decode

def verify_wallet_signature(address: str, signed_message: str, signature_hex: str) -> bool:
    """
    Verify that 'signature_hex' is a valid signature by 'address' over 'signed_message'.
    Tries SR25519 first (most common for SubWallet), then ED25519, then ECDSA.
    """
    if signature_hex.startswith("0x"):
        signature_hex = signature_hex[2:]
    try:
        sig_bytes = binascii.unhexlify(signature_hex)
    except binascii.Error:
        return False

    msg_bytes = signed_message.encode("utf-8")

    try:
        pubkey_hex = ss58_decode(address)  # hex without 0x
        pubkey = bytes.fromhex(pubkey_hex)
    except Exception:
        return False

    for kptype in (KeypairType.SR25519, KeypairType.ED25519, KeypairType.ECDSA):
        try:
            kp = Keypair(public_key=pubkey, ss58_address=address, crypto_type=kptype)
            if kp.verify(msg_bytes, sig_bytes):
                return True
        except Exception:
            pass
    return False


router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_PREFIX = "BidDrop login challenge: "

# ----------------------------
# 1) Issue login challenge
# ----------------------------
@router.post("/nonce")
def issue_nonce(payload: dict, db: Session = Depends(get_db)):
    address_raw = (payload.get("wallet_address") or "").strip()
    if not address_raw:
        raise HTTPException(status_code=400, detail="wallet_address is required")

    # Normalize server-side
    try:
        address = normalize_address(address_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SS58 address")

    nonce = secrets.token_hex(16)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    row = db.execute(text("""
        INSERT INTO login_nonces (address, nonce, expires_at)
        VALUES (:address, :nonce, :expires_at)
        ON CONFLICT (address)
        DO UPDATE SET nonce = EXCLUDED.nonce, expires_at = EXCLUDED.expires_at
        RETURNING address, nonce, expires_at
    """), {"address": address, "nonce": nonce, "expires_at": expires_at}).mappings().first()
    db.commit()

    message_to_sign = f"{LOGIN_PREFIX}{row['nonce']}"
   
    exp_val = row["expires_at"]

    if isinstance(exp_val, str):
        exp_val = datetime.fromisoformat(exp_val)

    exp_iso = exp_val.astimezone(timezone.utc)

    return {
        "wallet_address": row["address"],   # canonical
        "nonce": row["nonce"],
        "message_to_sign": message_to_sign,
        "expires_at": exp_iso.isoformat().replace("+00:00", "Z"),
    }


# ----------------------------
# 2) Verify signature
# ----------------------------
@router.post("/verify")
def verify_signature(payload: dict, db: Session = Depends(get_db)):
    address_raw = (payload.get("wallet_address") or "").strip()
    signature_hex = (payload.get("signature") or "").strip()
    signed_message = (payload.get("signed_message") or "").strip()

    if not address_raw or not signature_hex or not signed_message:
        raise HTTPException(status_code=400, detail="wallet_address, signature and signed_message are required")

    # Normalize first
    try:
        address = normalize_address(address_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SS58 address")

    # Load nonce for canonical address
    row = db.execute(text(
        "SELECT nonce, expires_at FROM login_nonces WHERE address = :address"
    ), {"address": address}).mappings().first()
    if not row:
        raise HTTPException(status_code=400, detail="No active login challenge for this address. Request a new nonce.")

    # Check TTL
    exp_val = row["expires_at"]

    if isinstance(exp_val, str):
        exp_val = datetime.fromisoformat(exp_val)

    expires_at_db = exp_val.astimezone(timezone.utc)
    if datetime.now(timezone.utc) > expires_at_db:
        db.execute(text("DELETE FROM login_nonces WHERE address = :address"), {"address": address})
        db.commit()
        raise HTTPException(status_code=400, detail="Login challenge expired. Request a new nonce.")

    # Must match the server-issued message exactly
    expected_message = f"{LOGIN_PREFIX}{row['nonce']}"
    if signed_message != expected_message:
        raise HTTPException(status_code=400, detail="Signed message mismatch")

    # Verify signature (as אצלך)
    ok = verify_wallet_signature(address=address, signed_message=signed_message, signature_hex=signature_hex)
    if not ok:
        raise HTTPException(status_code=401, detail="Signature verification failed")

    # Upsert user by wallet_address
    user_row = db.execute(text("""
        INSERT INTO users (id, wallet_address, role, created_at, updated_at)
        VALUES (gen_random_uuid(), :wa, 'sender', NOW(), NOW())
        ON CONFLICT (wallet_address)
        DO UPDATE SET updated_at = NOW()
        RETURNING id, wallet_address, role
    """), {"wa": address}).mappings().first()

    # Invalidate the nonce
    db.execute(text("DELETE FROM login_nonces WHERE address = :address"), {"address": address})
    db.commit()

    token = create_access_token(subject=address)

    print("VERIFY OK for", address)
    print("JWT len:", len(token))

    return {
        "user": {
            "id": str(user_row["id"]),
            "wallet_address": user_row["wallet_address"],  # canonical
            "role": user_row["role"],
        },
        "access_token": token,
        "token_type": "bearer",
    }

