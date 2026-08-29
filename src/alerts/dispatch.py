"""Real alert dispatch — SMS (Twilio), Telegram (Bot API), and a generic
webhook — for CRITICAL-severity thermal events. Each channel is entirely
optional: it's only usable once its credentials are set in `.env` (see
.env.example); with nothing configured, `send_*()` returns a clear
"not configured" result rather than raising, so the dashboard can show a
helpful message instead of a stack trace.

This is a thin, direct wrapper over each provider's plain REST API via
`requests` — no provider SDK dependency (e.g. the `twilio` package) added
just for this. Nothing here is called automatically; every send is a
human clicking a "Send Now" button in the dashboard.
"""
from __future__ import annotations

import requests

import config

TWILIO_SEND_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
REQUEST_TIMEOUT_S = 10


def sms_configured() -> bool:
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN
                and config.TWILIO_FROM_NUMBER and config.ALERT_SMS_TO_NUMBER)


def telegram_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def webhook_configured() -> bool:
    return bool(config.ALERT_WEBHOOK_URL)


def send_sms(body: str) -> dict:
    """Sends `body` via Twilio's SMS REST API to config.ALERT_SMS_TO_NUMBER.
    Returns {"ok": bool, "detail": str} — never raises for a missing
    config or a failed HTTP call, so the caller can always show a result."""
    if not sms_configured():
        return {"ok": False, "detail": "Twilio not configured — set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                                        "TWILIO_FROM_NUMBER, and ALERT_SMS_TO_NUMBER in .env."}
    url = TWILIO_SEND_URL.format(sid=config.TWILIO_ACCOUNT_SID)
    try:
        resp = requests.post(
            url, auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            data={"To": config.ALERT_SMS_TO_NUMBER, "From": config.TWILIO_FROM_NUMBER, "Body": body},
            timeout=REQUEST_TIMEOUT_S,
        )
        if resp.ok:
            sid = resp.json().get("sid", "?")
            return {"ok": True, "detail": f"Sent — Twilio message SID {sid}."}
        return {"ok": False, "detail": f"Twilio rejected the request (HTTP {resp.status_code}): {resp.text[:300]}"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "detail": f"SMS send failed: {exc}"}


def send_telegram(text: str) -> dict:
    """Sends `text` (Telegram Markdown) via the Bot API to
    config.TELEGRAM_CHAT_ID. Returns {"ok": bool, "detail": str}."""
    if not telegram_configured():
        return {"ok": False, "detail": "Telegram not configured — set TELEGRAM_BOT_TOKEN and "
                                        "TELEGRAM_CHAT_ID in .env."}
    url = TELEGRAM_SEND_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    try:
        resp = requests.post(
            url, json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=REQUEST_TIMEOUT_S,
        )
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.ok and payload.get("ok"):
            return {"ok": True, "detail": "Sent to Telegram."}
        return {"ok": False, "detail": f"Telegram rejected the request: {payload.get('description', resp.text[:300])}"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "detail": f"Telegram send failed: {exc}"}


def send_webhook(payload: dict) -> dict:
    """POSTs `payload` as JSON to config.ALERT_WEBHOOK_URL. Returns
    {"ok": bool, "detail": str}."""
    if not webhook_configured():
        return {"ok": False, "detail": "No webhook configured — set ALERT_WEBHOOK_URL in .env."}
    try:
        resp = requests.post(config.ALERT_WEBHOOK_URL, json=payload, timeout=REQUEST_TIMEOUT_S)
        if resp.ok:
            return {"ok": True, "detail": f"Webhook accepted (HTTP {resp.status_code})."}
        return {"ok": False, "detail": f"Webhook rejected the request (HTTP {resp.status_code}): {resp.text[:300]}"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "detail": f"Webhook send failed: {exc}"}
