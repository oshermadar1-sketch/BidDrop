# Backend/routes_devices.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from .Database.db import get_db
from Backend.auth_dep import get_current_user


try:
    from .models import DeviceToken  # type: ignore
    HAS_DEVICE_TOKENS = True
except Exception:
    HAS_DEVICE_TOKENS = False

router = APIRouter(prefix="/devices", tags=["devices"])

class DeviceRegisterIn(BaseModel):
    # תמיכה בשתי צורות קלט
    expo_push_token: Optional[str] = None
    provider: Optional[str] = Field(None, description="e.g. 'expo' or 'fcm'")
    token: Optional[str] = None
    platform: Optional[str] = Field(None, description="'ios' | 'android'")
    channel_id: Optional[str] = None
    app_build: Optional[str] = None

@router.post("/register")
def register_device(
    payload: DeviceRegisterIn,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    # חלץ user_id גם אם user הוא dict
    user_id = str(user["id"] if isinstance(user, dict) else getattr(user, "id"))

    # קלט גמיש
    expo_token = payload.expo_push_token or payload.token
    if not expo_token:
        raise HTTPException(status_code=400, detail="Missing expo push token")

    now = datetime.now(timezone.utc)

    # 1) עדכן את users.expo_push_token + push_token_updated_at
    upd = text("""
        UPDATE users
        SET expo_push_token = :tok,
            push_token_updated_at = :ts
        WHERE id = :uid
    """)
    db.execute(upd, {"tok": expo_token, "ts": now, "uid": user_id})

    # 2) אופציונלי: החזקת טבלת מכשירים (אם קיימת בפרויקט)
    if HAS_DEVICE_TOKENS:
        found = (
            db.query(DeviceToken)
              .filter(DeviceToken.user_id == user_id,
                      DeviceToken.provider == (payload.provider or "expo"),
                      DeviceToken.token == expo_token)
              .one_or_none()
        )
        if found:
            found.platform = payload.platform or found.platform
            found.channel_id = payload.channel_id or found.channel_id
            found.app_build = payload.app_build or found.app_build
            found.last_seen_at = now
            db.add(found)
        else:
            rec = DeviceToken(
                user_id=user_id,
                provider=payload.provider or "expo",
                token=expo_token,
                platform=payload.platform,
                channel_id=payload.channel_id,
                app_build=payload.app_build,
                last_seen_at=now,
                created_at=now,
            )
            db.add(rec)

    db.commit()
    return {"ok": True, "saved_to_users": True}

@router.get("/debug/my_token")
def debug_my_token(db: Session = Depends(get_db), user=Depends(get_current_user)):
    uid = str(user["id"] if isinstance(user, dict) else getattr(user, "id"))
    row = db.execute(text("SELECT expo_push_token, push_token_updated_at FROM users WHERE id = :uid"),
                     {"uid": uid}).mappings().first()
    return {"user_id": uid, "expo_push_token": row["expo_push_token"] if row else None,
            "updated_at": row["push_token_updated_at"] if row else None}

@router.post("/debug/push_me")
def push_me(
    title: str = "בדיקת פוש",
    body: str = "שלום 👋",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from .services.push import send_expo_async  # לוגים שם
    uid = str(user["id"] if isinstance(user, dict) else getattr(user, "id"))
    row = db.execute(text("SELECT expo_push_token FROM users WHERE id = :uid"), {"uid": uid}).first()
    tok = row[0] if row else None
    if not tok:
        raise HTTPException(400, "No expo token saved on user")
    import asyncio
    asyncio.get_event_loop().create_task(
        send_expo_async(tok, title, body, {"screen": "Home"})
    )
    return {"ok": True, "to": tok}
