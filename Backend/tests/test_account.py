"""Email accounts: password rules, hashing, email links and the token subject handling."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt

from Backend import auth_dep
from Backend.routes_account import check_password, clean_email
from Backend.services import mailer
from Backend.services.passwords import (
    hash_password,
    new_token,
    password_problems,
    token_hash,
    verify_password,
)


# ------------------------------- password rules -------------------------------

def test_strong_password_has_no_problems():
    assert password_problems("Biddrop2026") == []


@pytest.mark.parametrize("pw", ["short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"])
def test_weak_passwords_are_rejected(pw):
    assert password_problems(pw)
    with pytest.raises(HTTPException) as e:
        check_password(pw)
    assert e.value.status_code == 400


def test_hash_roundtrip_and_salting():
    h1, h2 = hash_password("Biddrop2026"), hash_password("Biddrop2026")
    assert h1 != h2                      # a fresh salt each time
    assert verify_password("Biddrop2026", h1)
    assert not verify_password("biddrop2026", h1)
    assert not verify_password("Biddrop2026", None)
    assert not verify_password("Biddrop2026", "not-a-hash")


def test_email_is_normalised_and_validated():
    assert clean_email("  Gal@Example.COM ") == "gal@example.com"
    for bad in ["", "no-at-sign", "a@b", "a @b.com"]:
        with pytest.raises(HTTPException):
            clean_email(bad)


# ------------------------------- email links -------------------------------

def test_tokens_are_random_and_hashed_consistently():
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 32
    assert token_hash(a) == token_hash(a) and token_hash(a) != token_hash(b)


def test_links_use_the_web_app_address(monkeypatch):
    monkeypatch.setenv("APP_WEB_URL", "https://biddrop-web.onrender.com/")
    assert mailer.verification_link("abc") == "https://biddrop-web.onrender.com/verify-email?token=abc"
    assert mailer.reset_link("xyz") == "https://biddrop-web.onrender.com/reset-password?token=xyz"


def test_without_api_key_nothing_is_sent(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert mailer.send_verification_email("someone@example.com", "abc") is False


# --------------------------- token subject handling ---------------------------

class _Rows:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class FakeDB:
    """Records the WHERE clause get_current_user uses and answers with one row."""

    def __init__(self, row):
        self.row, self.queries = row, []

    def execute(self, stmt, params=None):
        self.queries.append((str(stmt), params))
        return _Rows(self.row)


def _token(subject):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": subject, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=5)).timestamp())},
        auth_dep.JWT_SECRET,
        algorithm=auth_dep.JWT_ALG,
    )


def test_user_id_subject_is_looked_up_by_id():
    uid = "2f9d1a3c-5b2e-4c1d-9e8f-0a1b2c3d4e5f"
    db = FakeDB({"id": uid, "role": "sender"})
    me = auth_dep.get_current_user(db=db, authorization="Bearer " + _token(uid))
    assert me["id"] == uid
    sql, params = db.queries[0]
    assert "WHERE id = :uid" in sql and params == {"uid": uid}


def test_wallet_subject_is_looked_up_by_address():
    address = "5HjPGnuUN5BffGgUD7RZSiUa71Mv49UZAeUTMdpBnv43orgW"
    db = FakeDB({"id": "x", "wallet_address": address})
    auth_dep.get_current_user(db=db, authorization="Bearer " + _token(address))
    sql, params = db.queries[0]
    assert "WHERE wallet_address = :wa" in sql and params == {"wa": address}


def test_unknown_user_is_rejected():
    db = FakeDB(None)
    with pytest.raises(HTTPException) as e:
        auth_dep.get_current_user(db=db, authorization="Bearer " + _token("nobody"))
    assert e.value.status_code == 401
