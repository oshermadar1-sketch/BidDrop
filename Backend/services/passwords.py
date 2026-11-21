# Backend/services/passwords.py
# Password rules and hashing for email accounts (routes_account.py).
#
# Rules (the same ones the sign-up form shows): at least 8 characters, an upper-case
# letter, a lower-case letter and a digit. Hashing uses bcrypt with a per-password salt,
# so the database never holds the password itself.
import hashlib
import re
import secrets

import bcrypt

MIN_LENGTH = 8

# One entry per rule: (key, Hebrew description, check)
RULES = [
    ("length", f"לפחות {MIN_LENGTH} תווים", lambda p: len(p) >= MIN_LENGTH),
    ("upper", "אות גדולה באנגלית (A-Z)", lambda p: re.search(r"[A-Z]", p) is not None),
    ("lower", "אות קטנה באנגלית (a-z)", lambda p: re.search(r"[a-z]", p) is not None),
    ("digit", "ספרה אחת לפחות (0-9)", lambda p: re.search(r"[0-9]", p) is not None),
]


def password_problems(password: str) -> list[str]:
    """Hebrew descriptions of the rules the password breaks (empty when it is fine)."""
    return [text for _, text, check in RULES if not check(password or "")]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# ---- One-time tokens for email links (verification, password reset) ----
# The link carries the raw token; the database stores only its SHA-256, so a leaked
# database row cannot be turned into a working link.

def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
