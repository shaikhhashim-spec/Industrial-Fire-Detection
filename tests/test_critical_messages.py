from __future__ import annotations

import pytest

import config
from src.alerts.messages import (
    format_critical_alert_message,
    is_critical_alert,
    load_critical_dispatch_log,
    log_critical_dispatch,
    normalize_phone_number,
    send_batch_critical_alerts,
    send_critical_alert,
)


def _sample_alert(**overrides):
    base = {
        "event_id": "TH-TEST85",
        "grid_cell": "22.80_86.18",
        "latitude": 22.8046,
        "longitude": 86.1850,
        "risk_score": 88.5,
        "risk_level": "CRITICAL",
        "severity": "CRITICAL",
        "classification": "Likely Industrial Fire",
        "ai_confidence": 94.2,
        "frp": 15.6,
        "persistence_days": 24,
        "industrial_distance_km": 0.15,
        "status": "Requires immediate verification.",
    }
    base.update(overrides)
    return base


def test_normalize_phone_number():
    formatted, clean = normalize_phone_number("9967541336")
    assert formatted == "+919967541336"
    assert clean == "919967541336"

    formatted2, clean2 = normalize_phone_number("+919967541336")
    assert formatted2 == "+919967541336"
    assert clean2 == "919967541336"

    formatted3, clean3 = normalize_phone_number("09967541336")
    assert formatted3 == "+919967541336"
    assert clean3 == "919967541336"


def test_format_critical_alert_message_contains_all_details():
    alert = _sample_alert(risk_score=89.0, ai_confidence=95.5)
    msg = format_critical_alert_message(alert)

    assert "🚨 CRITICAL THERMAL EVENT DETECTED" in msg
    assert "Risk Score: 89.0/100 (CRITICAL)" in msg
    assert "AI Confidence: 95.5%" in msg
    assert "Status: Requires immediate verification." in msg
    assert "TH-TEST85" in msg
    assert "22.8046°N, 86.1850°E" in msg
    assert "FRP: 15.6 MW" in msg
    assert "Classification: Likely Industrial Fire" in msg


def test_is_critical_alert():
    assert is_critical_alert(_sample_alert(severity="CRITICAL", risk_score=80.0))
    assert is_critical_alert(_sample_alert(severity="HIGH", risk_score=78.0))
    assert not is_critical_alert(_sample_alert(severity="HIGH", risk_score=60.0, risk_level="HIGH"))
    assert not is_critical_alert(_sample_alert(severity="MODERATE", risk_score=30.0, risk_level="MODERATE"))


def test_send_critical_alert_non_critical_skipped():
    low_alert = _sample_alert(risk_score=60.0, severity="HIGH", risk_level="HIGH")
    res = send_critical_alert(low_alert, phone="9967541336", force=False)
    assert res["status"] == "skipped"
    assert "not CRITICAL" in res["reason"]


def test_send_critical_alert_critical_delivered_or_simulated():
    critical_alert = _sample_alert(risk_score=85.0, severity="CRITICAL")
    res = send_critical_alert(critical_alert, phone="9967541336")
    assert res["status"] in ("simulated", "delivered")
    assert res["recipient"] == "+919967541336"
    assert res["risk_score"] == 85.0
    assert res["severity"] == "CRITICAL"
    assert "message" in res


def test_send_critical_alert_force_bypass():
    low_alert = _sample_alert(risk_score=40.0, severity="LOW", risk_level="LOW")
    res = send_critical_alert(low_alert, phone="9967541336", force=True)
    assert res["status"] in ("simulated", "delivered")


def test_send_batch_critical_alerts_only_sends_critical():
    alerts = [
        _sample_alert(event_id="TH-LOW", risk_score=50.0, severity="MODERATE", risk_level="MODERATE"),
        _sample_alert(event_id="TH-CRIT-1", risk_score=85.0, severity="CRITICAL", risk_level="CRITICAL"),
        _sample_alert(event_id="TH-CRIT-2", risk_score=91.5, severity="CRITICAL", risk_level="CRITICAL"),
        _sample_alert(event_id="TH-HIGH", risk_score=65.0, severity="HIGH", risk_level="HIGH"),
    ]
    results = send_batch_critical_alerts(alerts, phone="9967541336", max_alerts=5)
    assert len(results) == 2
    dispatched_ids = [r["event_id"] for r in results]
    assert "TH-CRIT-1" in dispatched_ids
    assert "TH-CRIT-2" in dispatched_ids
    assert "TH-LOW" not in dispatched_ids
    assert "TH-HIGH" not in dispatched_ids
