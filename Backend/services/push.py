# services/push.py
# Expo push sender (HTTP v2).

from __future__ import annotations
import httpx
from typing import Optional, Dict, Any

EXPO_URL = "https://exp.host/--/api/v2/push/send"

async def send_expo_async(
    to: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    sound: str = "default",
    channel_id: str = "default",
) -> None:
    if not to:
        print("[PUSH] skip: empty token")
        return

    payload: Dict[str, Any] = {
        "to": to,
        "title": title,
        "body": body,
        "sound": sound,
        "channelId": channel_id,
        "data": data or {},
    }

    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(EXPO_URL, json=payload)
            try:
                js = r.json()
            except Exception:
                js = {"raw": r.text}
            print(f"[PUSH] Expo resp {r.status_code}: {js}")
    except Exception as e:
        print("[PUSH] http error:", repr(e))

def fire_and_forget(coro):
    try:
        import asyncio
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        import asyncio
        asyncio.run(coro)
