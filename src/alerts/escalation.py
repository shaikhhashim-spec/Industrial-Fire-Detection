"""Acknowledgement tracking and voice escalation for dispatched critical alerts.

The gap this closes: a text alert that nobody reads is the same as no alert.
Every critical dispatch is recorded here as awaiting acknowledgement. Once it
has gone unacknowledged past `config.ALERT_ESCALATE_AFTER_MIN`, it becomes
eligible for a phone call, which is much harder to ignore than an SMS.

Two deliberate safety properties:

* **A call is never placed on a timer alone.** `due()` only reports what is
  overdue; something has to call `place_call()`, which is a button in the
  dashboard. The `ALERT_AUTO_ESCALATE_CALL` opt-in exists, and even then
  `escalate_due()` has to be invoked.
* **Each alert escalates at most once.** The state moves
  awaiting_ack -> escalated (or -> acknowledged), so a page that reruns every
  few seconds cannot dial the same number repeatedly.

With no Twilio credentials the call is simulated and logged, exactly like the
SMS path, so the flow is demonstrable without spending money or ringing a real
phone.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

import requests

import config
from src.alerts import dispatch

logger = logging.getLogger(__name__)

TWILIO_CALL_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
MAX_ENTRIES = 200

AWAITING = "awaiting_ack"
ACKNOWLEDGED = "acknowledged"
ESCALATED = "escalated"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def load() -> list[dict[str, Any]]:
    path = config.ALERT_ESCALATION_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read the escalation log: %s", exc)
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    try:
        config.ALERT_ESCALATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.ALERT_ESCALATION_PATH.write_text(
            json.dumps(entries[:MAX_ENTRIES], indent=2, default=str), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not write the escalation log: %s", exc)


def record_dispatch(event: dict[str, Any], phone: str, channel: str = "message") -> dict[str, Any]:
    """Start the acknowledgement clock for one dispatched alert. Re-dispatching
    the same event restarts its clock rather than queueing a second escalation."""
    event_id = str(event.get("event_id") or event.get("grid_cell") or "UNKNOWN")
    entries = [e for e in load() if e.get("event_id") != event_id]
    entry = {
        "event_id": event_id,
        "phone": phone,
        "channel": channel,
        "risk_score": float(event.get("risk_score") or 0.0),
        "severity": str(event.get("severity") or event.get("risk_level") or "CRITICAL"),
        "title": event.get("title") or event.get("classification") or "Thermal event",
        "latitude": float(event.get("latitude") or 0.0),
        "longitude": float(event.get("longitude") or 0.0),
        "dispatched_at": _now().isoformat(),
        "state": AWAITING,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "escalated_at": None,
        "call_detail": None,
    }
    entries.insert(0, entry)
    _save(entries)
    return entry


def acknowledge(event_id: str, by: str = "analyst") -> dict[str, Any] | None:
    """Stop the clock. An acknowledged alert is never escalated."""
    entries = load()
    for entry in entries:
        if entry.get("event_id") == event_id:
            entry["state"] = ACKNOWLEDGED
            entry["acknowledged_at"] = _now().isoformat()
            entry["acknowledged_by"] = by
            _save(entries)
            return entry
    return None


def minutes_waiting(entry: dict[str, Any]) -> float:
    sent = _parse(entry.get("dispatched_at"))
    if sent is None:
        return 0.0
    return (_now() - sent).total_seconds() / 60.0


def pending() -> list[dict[str, Any]]:
    """Dispatched, not acknowledged, not yet escalated."""
    return [e for e in load() if e.get("state") == AWAITING]


def due(after_minutes: int | None = None) -> list[dict[str, Any]]:
    """Pending alerts past the acknowledgement window."""
    window = config.ALERT_ESCALATE_AFTER_MIN if after_minutes is None else after_minutes
    return [e for e in pending() if minutes_waiting(e) >= window]


def call_script(entry: dict[str, Any]) -> str:
    """What the recipient hears. Short, repeated once, and explicit that this is
    an unconfirmed satellite detection rather than a confirmed fire."""
    return (
        "This is an automated escalation from the Thermal Intelligence satellite monitoring system. "
        f"A critical thermal event, reference {entry.get('event_id')}, "
        f"was reported {int(minutes_waiting(entry))} minutes ago and has not been acknowledged. "
        f"Risk score {int(float(entry.get('risk_score') or 0))} out of 100. "
        f"Location, latitude {float(entry.get('latitude') or 0):.2f}, "
        f"longitude {float(entry.get('longitude') or 0):.2f}. "
        "This is a satellite detection awaiting ground verification, not a confirmed fire. "
        "Please open the dashboard and acknowledge the alert."
    )


def _twiml(text: str) -> str:
    safe = text.replace("&", "and").replace("<", "").replace(">", "")
    return f'<Response><Say voice="alice" language="en-IN">{safe}</Say><Pause length="1"/><Say voice="alice" language="en-IN">{safe}</Say></Response>'


def place_call(
    entry: dict[str, Any],
    phone: str | None = None,
    twilio_sid: str | None = None,
    twilio_token: str | None = None,
    twilio_from: str | None = None,
) -> dict[str, Any]:
    """Ring the recipient and read the escalation script. Returns a result dict
    and marks the entry escalated so it cannot dial twice."""
    from src.alerts.messages import normalize_phone_number

    to_number, _ = normalize_phone_number(phone or entry.get("phone"))
    script = call_script(entry)

    sid = twilio_sid or config.TWILIO_ACCOUNT_SID
    token = twilio_token or config.TWILIO_AUTH_TOKEN
    from_num = twilio_from or config.TWILIO_VOICE_FROM_NUMBER

    if sid and token and from_num:
        try:
            resp = requests.post(
                TWILIO_CALL_URL.format(sid=sid),
                auth=(sid, token),
                data={"To": to_number, "From": from_num, "Twiml": _twiml(script)},
                timeout=dispatch.REQUEST_TIMEOUT_S,
            )
            if resp.ok:
                call_sid = resp.json().get("sid", "?")
                result = {"status": "calling", "detail": f"Twilio call placed (SID {call_sid})"}
            else:
                result = {"status": "failed",
                          "detail": f"Twilio rejected the call (HTTP {resp.status_code}): {resp.text[:200]}"}
        except Exception as exc:  # a failed call must never take the dashboard down
            result = {"status": "failed", "detail": f"Call failed: {exc}"}
    else:
        result = {"status": "simulated",
                  "detail": "No voice credentials configured, so the call was logged rather than placed."}

    result.update({"event_id": entry.get("event_id"), "recipient": to_number,
                   "timestamp": _now().isoformat(), "script": script})

    if result["status"] != "failed":
        entries = load()
        for e in entries:
            if e.get("event_id") == entry.get("event_id"):
                e["state"] = ESCALATED
                e["escalated_at"] = result["timestamp"]
                e["call_detail"] = result["detail"]
                break
        _save(entries)
    return result


def escalate_due(after_minutes: int | None = None, phone: str | None = None) -> list[dict[str, Any]]:
    """Call every overdue alert once. Only reached from an explicit action or
    the ALERT_AUTO_ESCALATE_CALL opt-in, never from a bare page load."""
    return [place_call(entry, phone=phone) for entry in due(after_minutes)]
