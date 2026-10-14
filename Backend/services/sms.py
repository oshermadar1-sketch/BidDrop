# services/sms.py
# Simple SMS service. Falls back to console print if TWILIO_* env vars are missing.
# All comments in English.

import os

_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
_TWILIO_FROM = os.getenv("TWILIO_FROM")

_client = None
if _TWILIO_SID and _TWILIO_TOKEN and _TWILIO_FROM:
    try:
        from twilio.rest import Client
        _client = Client(_TWILIO_SID, _TWILIO_TOKEN)
    except Exception as e:
        print(f"[SMS] Failed to init Twilio client: {e} (using DEV mode)")
        _client = None


def send_sms(to_e164: str, body: str) -> str:
    """
    Sends an SMS. For Hebrew texts keep messages concise (UCS-2 payload).
    Returns a message id (Twilio SID or DEV-*).
    """
    if not to_e164:
        raise ValueError("send_sms: empty destination")

    if _client is None:
        # DEV fallback: just print to server logs.
        print(f"[SMS-DEV] to={to_e164} body={body}")
        return "DEV-SID"

    msg = _client.messages.create(
        to=to_e164,
        from_=_TWILIO_FROM,
        body=body,
    )
    return msg.sid
