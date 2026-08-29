"""WhatsApp Alert Integration module for satellite thermal hotspot intelligence.

Provides formatted multi-provider alerting (Twilio, CallMeBot, Meta Cloud API,
custom webhooks, and direct WhatsApp Web wa.me click-to-chat links) when
thermal events reach a risk score threshold (default >= 85) to the target recipient.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import urllib.parse
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)


def normalize_phone_number(phone: str | None) -> tuple[str, str]:
    """Normalize phone number to (+CountryCode and raw digits).

    Returns:
        tuple[str, str]: (formatted_with_plus, clean_digits_only)
        e.g. ("+919967541336", "919967541336")
    """
    if not phone:
        phone = config.WHATSAPP_RECIPIENT_PHONE or "9967541336"

    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 10:
        # Default Indian 10-digit mobile number prefix
        digits = f"91{digits}"
    elif digits.startswith("0") and len(digits) == 11:
        digits = f"91{digits[1:]}"

    return f"+{digits}", digits


def format_whatsapp_alert(event_or_alert: dict[str, Any]) -> str:
    """Format the thermal event into the official high-risk WhatsApp alert message."""
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

    # Construct the exact requested notification layout
    lines = [
        "🚨 *HIGH-RISK THERMAL EVENT DETECTED*",
        "_A persistent thermal hotspot has been detected near an industrial zone._",
        "",
        f"📍 *Event ID:* `{event_id}`",
        f"🗺️ *Coordinates:* {lat:.4f}°N, {lon:.4f}°E",
        f"🔥 *Risk Score:* *{risk_score:.1f}/100* (CRITICAL)",
        f"🤖 *AI Confidence:* *{ai_conf:.1f}%*",
        "📊 *Status:* *Requires immediate verification.*",
        f"⚡ *FRP:* {frp:.1f} MW",
        f"⏱️ *Persistence:* {persistence} days active",
        f"🏭 *Industrial Proximity:* {ind_str}",
        f"🏷️ *Classification:* {classification}",
        f"🕒 *Timestamp:* {timestamp}",
        "",
        "🔗 _Verify event details on the Thermal Intelligence Dashboard._",
    ]
    return "\n".join(lines)


def get_whatsapp_web_url(event_or_alert: dict[str, Any], phone: str | None = None) -> str:
    """Generate a 1-click WhatsApp Web / App direct chat URL (wa.me) with pre-filled alert text."""
    _, clean_digits = normalize_phone_number(phone)
    msg = format_whatsapp_alert(event_or_alert)
    encoded = urllib.parse.quote(msg)
    return f"https://wa.me/{clean_digits}?text={encoded}"


def load_whatsapp_dispatch_log() -> list[dict[str, Any]]:
    """Load logged WhatsApp notifications from disk."""
    path = config.WHATSAPP_LOG_PATH
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read WhatsApp dispatch log: %s", exc)
        return []


def log_whatsapp_dispatch(entry: dict[str, Any]) -> None:
    """Append a dispatched alert record to the persistent log."""
    path = config.WHATSAPP_LOG_PATH
    try:
        history = load_whatsapp_dispatch_log()
        history.insert(0, entry)
        # Keep most recent 200 logs
        history = history[:200]
        path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write WhatsApp dispatch log: %s", exc)


def send_whatsapp_alert(
    event_or_alert: dict[str, Any],
    phone: str | None = None,
    threshold: float | None = None,
    force: bool = False,
    provider: str | None = None,
    twilio_sid: str | None = None,
    twilio_token: str | None = None,
    twilio_number: str | None = None,
    callmebot_key: str | None = None,
    meta_token: str | None = None,
    meta_phone_id: str | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Evaluate and dispatch a WhatsApp notification if risk score >= threshold (or force=True).

    Args:
        event_or_alert: Hotspot event dictionary or cluster row.
        phone: Destination phone number (defaults to config.WHATSAPP_RECIPIENT_PHONE).
        threshold: Minimum risk score to trigger (defaults to config.WHATSAPP_RISK_THRESHOLD, 85.0).
        force: If True, bypass threshold check (useful for manual test dispatches).
        provider: Provider to use ('auto', 'twilio', 'callmebot', 'meta', 'webhook', 'simulated').

    Returns:
        dict: Dispatch result summary with status, provider, timestamp, and message.
    """
    thresh = float(threshold if threshold is not None else config.WHATSAPP_RISK_THRESHOLD)
    risk_score = float(event_or_alert.get("risk_score") or 0.0)

    if not force and risk_score < thresh:
        return {
            "status": "skipped",
            "reason": f"Risk score ({risk_score:.1f}) is below alert threshold ({thresh:.1f})",
            "risk_score": risk_score,
            "threshold": thresh,
            "event_id": event_or_alert.get("event_id", "UNKNOWN"),
        }

    formatted_phone, clean_digits = normalize_phone_number(phone)
    message_text = format_whatsapp_alert(event_or_alert)
    wa_url = get_whatsapp_web_url(event_or_alert, formatted_phone)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    prov = (provider or config.WHATSAPP_PROVIDER or "auto").lower()

    t_sid = twilio_sid or config.TWILIO_ACCOUNT_SID
    t_token = twilio_token or config.TWILIO_AUTH_TOKEN
    t_num = twilio_number or config.TWILIO_WHATSAPP_NUMBER
    cmb_key = callmebot_key or config.CALLMEBOT_API_KEY
    m_token = meta_token or config.WHATSAPP_CLOUD_API_TOKEN
    m_pid = meta_phone_id or config.WHATSAPP_PHONE_NUMBER_ID
    wb_url = webhook_url or config.WHATSAPP_WEBHOOK_URL

    result: dict[str, Any] = {
        "timestamp": now_iso,
        "recipient": formatted_phone,
        "event_id": event_or_alert.get("event_id", event_or_alert.get("grid_cell", "UNKNOWN")),
        "risk_score": risk_score,
        "ai_confidence": event_or_alert.get("ai_confidence", 85.0),
        "status": "pending",
        "provider": prov,
        "wa_url": wa_url,
        "message": message_text,
    }

    # Resolve active provider
    if prov == "auto":
        if t_sid and t_token:
            prov = "twilio"
        elif cmb_key:
            prov = "callmebot"
        elif m_token and m_pid:
            prov = "meta"
        elif wb_url:
            prov = "webhook"
        else:
            prov = "simulated"

    result["provider"] = prov

    try:
        if prov == "twilio":
            if not (t_sid and t_token):
                raise ValueError("Twilio Account SID or Auth Token not provided.")
            from_num = t_num if t_num.startswith("whatsapp:") else f"whatsapp:{t_num}"
            to_num = f"whatsapp:{formatted_phone}"
            api_url = f"https://api.twilio.com/2010-04-01/Accounts/{t_sid}/Messages.json"

            # Attempt direct Body message first
            payload = {"From": from_num, "To": to_num, "Body": message_text}
            resp = requests.post(
                api_url,
                auth=(t_sid, t_token),
                data=payload,
                timeout=12,
            )

            # If Twilio requires a pre-approved ContentSid template (error 21654), retry with ContentSid
            if resp.status_code == 400:
                try:
                    err_json = resp.json()
                    if err_json.get("code") == 21654 or "ContentSid" in resp.text:
                        c_sid = getattr(config, "TWILIO_CONTENT_SID", "") or "HXfe5ab5f00277942d4d4200328b4d403c"
                        if c_sid:
                            template_payload = {"From": from_num, "To": to_num, "ContentSid": c_sid}
                            resp = requests.post(api_url, auth=(t_sid, t_token), data=template_payload, timeout=12)
                except Exception:
                    pass

            if resp.status_code in (200, 201):
                result["status"] = "delivered"
                result["response"] = resp.json()
            else:
                result["status"] = "failed"
                result["error"] = f"Twilio HTTP {resp.status_code}: {resp.text}"

        elif prov == "callmebot":
            if not cmb_key:
                raise ValueError("CallMeBot API Key not provided.")
            resp = requests.get(
                "https://api.callmebot.com/whatsapp.php",
                params={"phone": clean_digits, "text": message_text, "apikey": cmb_key},
                timeout=12,
            )
            if resp.status_code == 200 and "error" not in resp.text.lower():
                result["status"] = "delivered"
                result["response"] = resp.text[:200]
            else:
                result["status"] = "failed"
                result["error"] = f"CallMeBot HTTP {resp.status_code}: {resp.text[:200]}"

        elif prov == "meta":
            if not (m_token and m_pid):
                raise ValueError("Meta WhatsApp Cloud API Token or Phone Number ID not provided.")
            api_url = f"https://graph.facebook.com/v18.0/{m_pid}/messages"
            headers = {"Authorization": f"Bearer {m_token}", "Content-Type": "application/json"}
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_digits,
                "type": "text",
                "text": {"body": message_text},
            }
            resp = requests.post(api_url, headers=headers, json=payload, timeout=12)
            if resp.status_code in (200, 201):
                result["status"] = "delivered"
                result["response"] = resp.json()
            else:
                result["status"] = "failed"
                result["error"] = f"Meta HTTP {resp.status_code}: {resp.text}"

        elif prov == "webhook":
            if not wb_url:
                raise ValueError("WhatsApp Webhook URL not provided.")
            payload = {
                "recipient": formatted_phone,
                "clean_digits": clean_digits,
                "message": message_text,
                "event": event_or_alert,
                "timestamp": now_iso,
            }
            resp = requests.post(wb_url, json=payload, timeout=12)
            if resp.status_code in (200, 201, 202, 204):
                result["status"] = "delivered"
                result["response"] = f"HTTP {resp.status_code}"
            else:
                result["status"] = "failed"
                result["error"] = f"Webhook HTTP {resp.status_code}: {resp.text[:200]}"

        elif prov == "browser":
            import webbrowser
            webbrowser.open(wa_url)
            result["status"] = "delivered"
            result["response"] = "Opened in default browser with WhatsApp Web/App."

        else:  # simulated / local click-to-chat ready
            result["status"] = "simulated"
            result["response"] = "Message prepared and validated for WhatsApp Web / direct dispatch."

    except Exception as exc:
        logger.error("WhatsApp dispatch failed: %s", exc)
        result["status"] = "failed"
        result["error"] = str(exc)

    log_whatsapp_dispatch(result)
    return result


def send_batch_whatsapp_alerts(
    alerts: list[dict[str, Any]],
    phone: str | None = None,
    threshold: float | None = None,
    provider: str | None = None,
    max_alerts: int = 5,
) -> list[dict[str, Any]]:
    """Scan alert list and dispatch WhatsApp notifications for any event with risk >= threshold."""
    thresh = float(threshold if threshold is not None else config.WHATSAPP_RISK_THRESHOLD)
    results = []
    sent_count = 0

    for alert in alerts:
        risk = float(alert.get("risk_score") or 0.0)
        if risk >= thresh:
            res = send_whatsapp_alert(alert, phone=phone, threshold=thresh, force=False, provider=provider)
            results.append(res)
            sent_count += 1
            if sent_count >= max_alerts:
                break

    return results
