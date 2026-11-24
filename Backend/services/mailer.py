# Backend/services/mailer.py
# Sends the account emails (verification link, password reset) through Resend.
#
# Configuration (environment):
#   RESEND_API_KEY  - API key from resend.com. Without it nothing is sent: the message is
#                     written to the log instead, which is enough for local development.
#   EMAIL_FROM      - sender shown to the user, e.g. "BidDrop <onboarding@resend.dev>".
#                     Resend's shared onboarding address can only deliver to the address of
#                     the Resend account itself; a verified domain is needed for other
#                     recipients.
#   APP_WEB_URL     - base address of the web app, used to build the links in the emails.
import logging
import os

import httpx

log = logging.getLogger("mailer")

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SEC = 10


def app_web_url() -> str:
    return (os.getenv("APP_WEB_URL") or "http://localhost:8081").rstrip("/")


def email_from() -> str:
    return os.getenv("EMAIL_FROM") or "BidDrop <onboarding@resend.dev>"


def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send one email. Returns True when Resend accepted it; never raises."""
    # Addresses saved from the profile form keep the user's capitals; Resend's test
    # sender compares the address exactly and refused "Name@gmail.com".
    to = (to or "").strip().lower()
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        log.warning("RESEND_API_KEY not set; email to %s not sent.\n%s", to, text)
        return False
    try:
        r = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"from": email_from(), "to": [to], "subject": subject, "html": html, "text": text},
            timeout=TIMEOUT_SEC,
        )
        if r.status_code >= 300:
            log.error("Resend refused the email to %s: %s %s", to, r.status_code, r.text[:300])
            return False
        return True
    except httpx.HTTPError as e:
        log.error("Resend request failed for %s: %s", to, e)
        return False


def _layout(title: str, body: str, link: str, button: str) -> str:
    return f"""
<div dir="rtl" style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:auto;padding:24px;color:#0b0b0b">
  <h2 style="color:#475530;margin:0 0 12px">{title}</h2>
  <p style="font-size:15px;line-height:22px">{body}</p>
  <p style="margin:24px 0">
    <a href="{link}" style="background:#9bac70;color:#fff;text-decoration:none;padding:12px 22px;border-radius:12px;font-weight:700;display:inline-block">{button}</a>
  </p>
  <p style="font-size:12px;color:#6b7280">אם הכפתור לא עובד, אפשר להעתיק את הקישור:<br>{link}</p>
</div>
"""


def verification_link(raw_token: str) -> str:
    return f"{app_web_url()}/verify-email?token={raw_token}"


def reset_link(raw_token: str) -> str:
    return f"{app_web_url()}/reset-password?token={raw_token}"


def send_verification_email(to: str, raw_token: str) -> bool:
    link = verification_link(raw_token)
    body = "תודה שנרשמת ל-BidDrop. כדי לאמת את כתובת האימייל, לחץ/י על הכפתור. הקישור תקף ל-24 שעות."
    return send_email(
        to,
        "אימות כתובת האימייל - BidDrop",
        _layout("אימות אימייל", body, link, "אימות האימייל"),
        f"{body}\n{link}",
    )


def send_reset_email(to: str, raw_token: str) -> bool:
    link = reset_link(raw_token)
    body = "התקבלה בקשה לאיפוס הסיסמה בחשבון BidDrop שלך. הקישור תקף לשעה. אם לא ביקשת איפוס, אפשר להתעלם מההודעה."
    return send_email(
        to,
        "איפוס סיסמה - BidDrop",
        _layout("איפוס סיסמה", body, link, "בחירת סיסמה חדשה"),
        f"{body}\n{link}",
    )
