# routes_account.py
# Email + password accounts, next to the wallet login in routes_auth.py:
#   POST /auth/register             create an account, send a verification email, log in
#   POST /auth/login                email + password -> JWT
#   POST /auth/verify-email         consume the link from the verification email
#   POST /auth/resend-verification  (logged in) send the verification email again
#   POST /auth/forgot-password      send a password-reset link (always answers 200)
#   POST /auth/reset-password       consume the reset link and set a new password
#   POST /auth/link-wallet          (logged in) attach a SubWallet address, proven by a
#                                   signature over a login nonce, for payments
#
# Tokens issued here carry the user id as 'sub'; wallet tokens carry the address. The
# dependency in auth_dep.py accepts both, so old logins keep working.
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .Database.db import get_db
from .auth_dep import get_current_user
from .routes_auth import (
    LOGIN_PREFIX,
    create_access_token,
    normalize_address,
    verify_wallet_signature,
)
from .services import mailer
from .services.passwords import (
    hash_password,
    new_token,
    password_problems,
    token_hash,
    verify_password,
)

log = logging.getLogger("account")
router = APIRouter(prefix="/auth", tags=["account"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)

USER_COLUMNS = """
    id, wallet_address, role, email, phone, city, first_name, last_name, rating,
    first_login_completed, email_verified_at, (password_hash IS NOT NULL) AS has_password,
    created_at, updated_at
"""


def clean_email(raw: str | None) -> str:
    email = (raw or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="כתובת אימייל לא תקינה")
    return email


def check_password(raw: str | None) -> str:
    password = raw or ""
    problems = password_problems(password)
    if problems:
        raise HTTPException(status_code=400, detail="הסיסמה חייבת לכלול: " + ", ".join(problems))
    return password


def _user_out(row) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    return d


def _issue_token(db: Session, user_id, purpose: str, ttl: timedelta) -> str:
    """Create a one-time email token for the user and return the raw value for the link."""
    raw = new_token()
    db.execute(
        text("DELETE FROM email_tokens WHERE user_id = :uid AND purpose = :purpose"),
        {"uid": str(user_id), "purpose": purpose},
    )
    db.execute(
        text("""
            INSERT INTO email_tokens (id, user_id, purpose, token_hash, expires_at, created_at)
            VALUES (gen_random_uuid(), :uid, :purpose, :h, :exp, NOW())
        """),
        {"uid": str(user_id), "purpose": purpose, "h": token_hash(raw),
         "exp": datetime.now(timezone.utc) + ttl},
    )
    return raw


def _consume_token(db: Session, raw: str | None, purpose: str):
    """Return the user id of a valid, unused token of this purpose, and mark it used."""
    if not raw:
        raise HTTPException(status_code=400, detail="חסר קוד בקישור")
    row = db.execute(
        text("""
            UPDATE email_tokens SET used_at = NOW()
            WHERE token_hash = :h AND purpose = :purpose AND used_at IS NULL
              AND expires_at > NOW()
            RETURNING user_id
        """),
        {"h": token_hash(raw), "purpose": purpose},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=400, detail="הקישור אינו תקף או שפג תוקפו. אפשר לבקש קישור חדש.")
    return row["user_id"]


# ----------------------------- register / login -----------------------------

@router.post("/register")
def register(payload: dict, db: Session = Depends(get_db)):
    email = clean_email(payload.get("email"))
    password = check_password(payload.get("password"))

    existing = db.execute(
        text("SELECT id, password_hash, wallet_address FROM users WHERE lower(email) = :email"),
        {"email": email},
    ).mappings().first()
    if existing:
        if existing["password_hash"]:
            raise HTTPException(status_code=409, detail="כתובת האימייל כבר רשומה. אפשר להתחבר או לאפס סיסמה.")
        # The email belongs to an account that was opened with a wallet and has no password
        # yet. Nobody can claim it by just typing the email: we send a set-password link to
        # that address (the reset flow), and the wallet login itself offers "set a password".
        raw = _issue_token(db, existing["id"], "reset", RESET_TTL)
        db.commit()
        sent = mailer.send_reset_email(email, raw)
        return {
            "existing_wallet_account": True,
            "link_sent": sent,
            "detail": "כתובת האימייל שייכת לחשבון שנפתח עם ארנק SubWallet. "
                      + ("שלחנו לאימייל קישור לקביעת סיסמה." if sent else "")
                      + " אפשר גם להתחבר עם SubWallet ולקבוע סיסמה מהמסך הראשי.",
        }

    row = db.execute(
        text(f"""
            INSERT INTO users (id, role, email, password_hash, created_at, updated_at)
            VALUES (gen_random_uuid(), 'sender', :email, :ph, NOW(), NOW())
            RETURNING {USER_COLUMNS}
        """),
        {"email": email, "ph": hash_password(password)},
    ).mappings().first()

    raw = _issue_token(db, row["id"], "verify", VERIFY_TTL)
    db.commit()
    sent = mailer.send_verification_email(email, raw)

    return {
        "user": _user_out(row),
        "access_token": create_access_token(subject=str(row["id"])),
        "token_type": "bearer",
        "verification_sent": sent,
    }


@router.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    email = clean_email(payload.get("email"))
    password = payload.get("password") or ""

    row = db.execute(
        text(f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE lower(email) = :email"),
        {"email": email},
    ).mappings().first()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="אימייל או סיסמה שגויים")

    out = _user_out(row)
    out.pop("password_hash", None)
    return {
        "user": out,
        "access_token": create_access_token(subject=out["id"]),
        "token_type": "bearer",
    }


# ------------------------------ email verification ------------------------------

@router.post("/verify-email")
def verify_email(payload: dict, db: Session = Depends(get_db)):
    user_id = _consume_token(db, payload.get("token"), "verify")
    db.execute(
        text("UPDATE users SET email_verified_at = COALESCE(email_verified_at, NOW()), updated_at = NOW() WHERE id = :uid"),
        {"uid": str(user_id)},
    )
    db.commit()
    return {"ok": True}


@router.post("/resend-verification")
def resend_verification(db: Session = Depends(get_db), me=Depends(get_current_user)):
    if not me.get("email"):
        raise HTTPException(status_code=400, detail="לחשבון אין כתובת אימייל")
    if me.get("email_verified_at"):
        return {"ok": True, "already_verified": True}
    raw = _issue_token(db, me["id"], "verify", VERIFY_TTL)
    db.commit()
    sent = mailer.send_verification_email(me["email"], raw)
    return {"ok": True, "sent": sent}


# -------------------------------- password reset --------------------------------

@router.post("/forgot-password")
def forgot_password(payload: dict, db: Session = Depends(get_db)):
    """Always answers OK, so the form does not reveal which emails have accounts."""
    try:
        email = clean_email(payload.get("email"))
    except HTTPException:
        return {"ok": True}
    row = db.execute(
        text("SELECT id FROM users WHERE lower(email) = :email AND password_hash IS NOT NULL"),
        {"email": email},
    ).mappings().first()
    if row:
        raw = _issue_token(db, row["id"], "reset", RESET_TTL)
        db.commit()
        mailer.send_reset_email(email, raw)
    return {"ok": True}


@router.post("/reset-password")
def reset_password(payload: dict, db: Session = Depends(get_db)):
    password = check_password(payload.get("password"))
    user_id = _consume_token(db, payload.get("token"), "reset")
    db.execute(
        text("UPDATE users SET password_hash = :ph, updated_at = NOW() WHERE id = :uid"),
        {"ph": hash_password(password), "uid": str(user_id)},
    )
    db.commit()
    return {"ok": True}


# ---------------------------------- set password ----------------------------------

@router.post("/set-password")
def set_password(payload: dict, db: Session = Depends(get_db), me=Depends(get_current_user)):
    """
    Give the logged-in account a password, so it can also sign in with email + password.
    Wallet accounts (no password yet) only need to be logged in; an account that already
    has a password must send the current one as well.
    """
    password = check_password(payload.get("password"))
    email = (me.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="קודם יש להוסיף כתובת אימייל לפרופיל")
    row = db.execute(text("SELECT password_hash FROM users WHERE id = :uid"), {"uid": str(me["id"])}).mappings().first()
    if row and row["password_hash"]:
        if not verify_password(payload.get("current_password") or "", row["password_hash"]):
            raise HTTPException(status_code=401, detail="הסיסמה הנוכחית שגויה")
    db.execute(
        text("UPDATE users SET password_hash = :ph, updated_at = NOW() WHERE id = :uid"),
        {"ph": hash_password(password), "uid": str(me["id"])},
    )
    db.commit()
    return {"ok": True, "email": email}


# ---------------------------------- link wallet ----------------------------------

@router.post("/link-wallet")
def link_wallet(payload: dict, db: Session = Depends(get_db), me=Depends(get_current_user)):
    """
    Attach a wallet to the logged-in account. The app first calls POST /auth/nonce for the
    address and has the wallet sign the challenge, exactly like the wallet login; here the
    signature proves the user controls the wallet before it is used for payments.
    """
    address_raw = (payload.get("wallet_address") or "").strip()
    signature_hex = (payload.get("signature") or "").strip()
    signed_message = (payload.get("signed_message") or "").strip()
    if not address_raw or not signature_hex or not signed_message:
        raise HTTPException(status_code=400, detail="wallet_address, signature and signed_message are required")
    try:
        address = normalize_address(address_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SS58 address")

    row = db.execute(
        text("SELECT nonce, expires_at FROM login_nonces WHERE address = :address"),
        {"address": address},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=400, detail="No active challenge for this address. Request a new nonce.")
    exp_val = row["expires_at"]
    if isinstance(exp_val, str):
        exp_val = datetime.fromisoformat(exp_val)
    if datetime.now(timezone.utc) > exp_val.astimezone(timezone.utc):
        db.execute(text("DELETE FROM login_nonces WHERE address = :address"), {"address": address})
        db.commit()
        raise HTTPException(status_code=400, detail="Challenge expired. Request a new nonce.")
    if signed_message != f"{LOGIN_PREFIX}{row['nonce']}":
        raise HTTPException(status_code=400, detail="Signed message mismatch")
    if not verify_wallet_signature(address=address, signed_message=signed_message, signature_hex=signature_hex):
        raise HTTPException(status_code=401, detail="Signature verification failed")

    owner = db.execute(
        text("SELECT id FROM users WHERE wallet_address = :wa"), {"wa": address}
    ).mappings().first()
    if owner and str(owner["id"]) != str(me["id"]):
        raise HTTPException(status_code=409, detail="הארנק הזה כבר מקושר לחשבון אחר")

    updated = db.execute(
        text(f"""
            UPDATE users SET wallet_address = :wa, updated_at = NOW()
            WHERE id = :uid
            RETURNING {USER_COLUMNS}
        """),
        {"wa": address, "uid": str(me["id"])},
    ).mappings().first()
    db.execute(text("DELETE FROM login_nonces WHERE address = :address"), {"address": address})
    db.commit()
    return {"user": _user_out(updated)}
