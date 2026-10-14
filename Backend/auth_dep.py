# auth_dep.py
# Dependency that authenticates the request using a Bearer JWT,
# decodes it, and returns the current user loaded from the DB.

from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
import os

from .Database.db import get_db

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PROD")
JWT_ALG = "HS256"

def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None)
):
    # Expect: Authorization: Bearer <token>
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # In our JWT, 'sub' stores the canonical wallet address
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload (no sub)")

    # Optional: double-check exp (jose already enforces it)
    exp = payload.get("exp")
    if exp and datetime.now(timezone.utc).timestamp() > float(exp):
        raise HTTPException(status_code=401, detail="Token expired")

    # Load the user by wallet_address and return all relevant fields.
    row = db.execute(text("""
        SELECT
            id,
            wallet_address,
            role,
            email,
            phone,
            city,
            first_name,
            last_name,
            rating,
            first_login_completed,
            created_at,
            updated_at
        FROM users
        WHERE wallet_address = :wa
    """), {"wa": sub}).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(row)

