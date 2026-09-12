"""Critical Alert Notification and Messaging Module for satellite thermal intelligence.

Provides formatted SMS and multi-channel messaging alerts when thermal events
reach CRITICAL severity (Risk Score >= 76 or severity == "CRITICAL").
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any

import requests

import config
from src.alerts import dispatch

logger = logging.getLogger(__name__)


#: Stands in when no recipient is configured. Obviously synthetic, so it can
#: never be mistaken for a real number and no provider will accept it.
PLACEHOLDER_PHONE = "9000000000"


def normalize_phone_number(phone: str | None) -> tuple[str, str]:
    """Normalize phone number to (+CountryCode and raw digits).

    Returns:
        tuple[str, str]: (formatted_with_plus, clean_digits_only)
        e.g. ("+919000000000", "919000000000")
    """
    if not phone:
        phone = config.ALERT_RECIPIENT_PHONE or PLACEHOLDER_PHONE

    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 10:
        # Default Indian 10-digit mobile number prefix
        digits = f"91{digits}"
    elif digits.startswith("0") and len(digits) == 11:
        digits = f"91{digits[1:]}"

    return f"+{digits}", digits


def format_critical_alert_message(event_or_alert: dict[str, Any]) -> str:
    """Format the thermal event into a high-priority critical text/SMS alert message."""
    event_id = event_or_alert.get("event_id") or event_or_alert.get("grid_cell") or "UNKNOWN-EVENT"
    lat = float(event_or_alert.get("latitude") or 0.0)
    lon = float(event_or_alert.get("longitude") or 0.0)
    risk_score = float(event_or_alert.get("risk_score") or 0.0)

    # Compute AI Confidence percentage
    ai_conf = event_or_alert.get("ai_confidence")
    if ai_conf is None:
        ml_c = event_or_alert.get("ml_confidence")
        if ml_c is not None:
            ai_conf = float(ml_c) * 100 if float(ml_c) <= 1.0 else float(ml_c)
        else:
            ai_conf = float(event_or_alert.get("avg_confidence") or 85.0)
    else:
        ai_conf = float(ai_conf)

    classification = event_or_alert.get("classification") or event_or_alert.get("dominant_label") or "Likely Industrial Thermal Source"
    frp = float(event_or_alert.get("frp") or event_or_alert.get("avg_frp") or event_or_alert.get("max_frp") or 0.0)
    persistence = event_or_alert.get("persistence_days") or event_or_alert.get(f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d") or 0
    ind_dist = event_or_alert.get("industrial_distance_km")
    ind_str = f"{float(ind_dist):.2f} km" if ind_dist is not None and str(ind_dist) != "nan" else "Within Industrial Zone"
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "🚨 CRITICAL THERMAL EVENT DETECTED",
        "A high-priority persistent hotspot requires immediate verification.",
        "",
        f"Event ID: {event_id}",
        f"Coordinates: {lat:.4f}°N, {lon:.4f}°E",
        f"Risk Score: {risk_score:.1f}/100 (CRITICAL)",
        f"AI Confidence: {ai_conf:.1f}%",
        "Status: Requires immediate verification.",
        f"FRP: {frp:.1f} MW | Persistence: {persistence}d active",
        f"Industrial Proximity: {ind_str}",
        f"Classification: {classification}",
        f"Timestamp: {timestamp}",
        "",
        "Thermal Intelligence System Alert",
    ]
    return "\n".join(lines)


def load_critical_dispatch_log() -> list[dict[str, Any]]:
    """Load logged critical message dispatches from disk."""
    path = config.ALERT_LOG_PATH
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read critical dispatch log: %s", exc)
        return []


def log_critical_dispatch(entry: dict[str, Any]) -> None:
    """Append a dispatched alert record to the persistent log."""
    path = config.ALERT_LOG_PATH
    try:
        history = load_critical_dispatch_log()
        history.insert(0, entry)
        # Keep most recent 200 logs
        history = history[:200]
        path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write critical dispatch log: %s", exc)


def is_critical_alert(event_or_alert: dict[str, Any]) -> bool:
    """Check if event/alert qualifies as CRITICAL severity."""
    severity = str(event_or_alert.get("severity") or "").upper()
    risk_level = str(event_or_alert.get("risk_level") or "").upper()
    risk_score = float(event_or_alert.get("risk_score") or 0.0)
    return severity == "CRITICAL" or risk_level == "CRITICAL" or risk_score >= config.ALERT_CRITICAL_RISK_MIN


def send_critical_alert(
    event_or_alert: dict[str, Any],
    phone: str | None = None,
    force: bool = False,
    twilio_sid: str | None = None,
    twilio_token: str | None = None,
    twilio_from: str | None = None,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Evaluate and dispatch a message notification if alert is CRITICAL (or force=True).

    Args:
        event_or_alert: Hotspot event dictionary or cluster row.
        phone: Destination phone number (defaults to config.ALERT_RECIPIENT_PHONE).
        force: If True, bypass critical severity check (for manual test dispatches).

    Returns:
        dict: Dispatch result summary with status, channels, timestamp, and message.
    """
    risk_score = float(event_or_alert.get("risk_score") or 0.0)
    severity = str(event_or_alert.get("severity") or event_or_alert.get("risk_level") or "UNKNOWN").upper()
    event_id = event_or_alert.get("event_id", event_or_alert.get("grid_cell", "UNKNOWN"))

    if not force and not is_critical_alert(event_or_alert):
        return {
            "status": "skipped",
            "reason": f"Alert is not CRITICAL (severity: {severity}, risk: {risk_score:.1f} < {config.ALERT_CRITICAL_RISK_MIN})",
            "risk_score": risk_score,
            "severity": severity,
            "event_id": event_id,
        }

    formatted_phone, clean_digits = normalize_phone_number(phone)
    if clean_digits.endswith(PLACEHOLDER_PHONE):
        return {
            "status": "unconfigured",
            "reason": "No recipient phone number is set. Add ALERT_RECIPIENT_PHONE to .env, or enter "
                      "one on the Settings page, before dispatching.",
            "risk_score": risk_score,
            "severity": severity,
            "event_id": event_id,
        }
    message_text = format_critical_alert_message(event_or_alert)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    channels_dispatched: list[str] = []
    details: list[str] = []

    # 1. Attempt Twilio SMS
    # Check if overrides provided or config available
    sid = twilio_sid or config.TWILIO_ACCOUNT_SID
    token = twilio_token or config.TWILIO_AUTH_TOKEN
    from_num = twilio_from or config.TWILIO_FROM_NUMBER

    if sid and token and from_num:
        try:
            url = dispatch.TWILIO_SEND_URL.format(sid=sid)
            resp = requests.post(
                url,
                auth=(sid, token),
                data={"To": formatted_phone, "From": from_num, "Body": message_text},
                timeout=dispatch.REQUEST_TIMEOUT_S,
            )
            if resp.ok:
                msg_sid = resp.json().get("sid", "?")
                channels_dispatched.append("sms")
                details.append(f"SMS delivered (Twilio SID: {msg_sid})")
            else:
                details.append(f"SMS rejected (HTTP {resp.status_code}): {resp.text[:150]}")
        except Exception as exc:
            details.append(f"SMS send error: {exc}")

    # 2. Attempt Telegram if configured
    if dispatch.telegram_configured(telegram_token, telegram_chat_id):
        tg_res = dispatch.send_telegram(f"🚨 *CRITICAL ALERT*\n\n{message_text}", telegram_token, telegram_chat_id)
        if tg_res.get("ok"):
            channels_dispatched.append("telegram")
            details.append("Telegram notification sent")
        else:
            details.append(f"Telegram failed: {tg_res.get('detail')}")

    # 3. Attempt Webhook if configured
    if dispatch.webhook_configured(webhook_url):
        wb_res = dispatch.send_webhook({
            "alert_type": "CRITICAL",
            "recipient": formatted_phone,
            "message": message_text,
            "event": event_or_alert,
            "timestamp": now_iso,
        }, webhook_url)
        if wb_res.get("ok"):
            channels_dispatched.append("webhook")
            details.append("Webhook payload delivered")
        else:
            details.append(f"Webhook failed: {wb_res.get('detail')}")

    # If no live API channel succeeded or was configured, record as simulated/prepared
    if channels_dispatched:
        status = "delivered"
        channel_str = "+".join(channels_dispatched)
    else:
        status = "simulated"
        channel_str = "message_log"
        details.append("Critical alert prepared & logged to system audit trail.")

    result: dict[str, Any] = {
        "timestamp": now_iso,
        "recipient": formatted_phone,
        "event_id": event_id,
        "risk_score": risk_score,
        "severity": "CRITICAL",
        "ai_confidence": event_or_alert.get("ai_confidence", 85.0),
        "status": status,
        "channel": channel_str,
        "detail": "; ".join(details),
        "message": message_text,
    }

    log_critical_dispatch(result)
    return result


def send_batch_critical_alerts(
    alerts: list[dict[str, Any]],
    phone: str | None = None,
    max_alerts: int = 5,
) -> list[dict[str, Any]]:
    """Scan alert list and automatically dispatch message notifications for CRITICAL alerts."""
    results = []
    sent_count = 0

    for alert in alerts:
        if is_critical_alert(alert):
            res = send_critical_alert(alert, phone=phone, force=False)
            results.append(res)
            sent_count += 1
            if sent_count >= max_alerts:
                break

    return results
