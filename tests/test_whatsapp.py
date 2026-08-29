from __future__ import annotations

import json
import pytest

import config
from src.alerts.whatsapp import (
    format_whatsapp_alert,
    get_whatsapp_web_url,
    load_whatsapp_dispatch_log,
    normalize_phone_number,
    send_batch_whatsapp_alerts,
    send_whatsapp_alert,
)


def _sample_alert(**overrides):
    base = {
        "event_id": "TH-TEST85",
        "grid_cell": "22.80_86.18",
        "latitude": 22.8046,
        "longitude": 86.1850,
        "risk_score": 88.5,
        "risk_level": "CRITICAL",
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


def test_format_whatsapp_alert_contains_all_spec_requirements():
    alert = _sample_alert(risk_score=89.0, ai_confidence=95.5)
    msg = format_whatsapp_alert(alert)

    # Check required text elements from user specification
    assert "🚨 *HIGH-RISK THERMAL EVENT DETECTED*" in msg
    assert "A persistent thermal hotspot has been detected near an industrial zone." in msg
    assert "Risk Score:* *89.0/100*" in msg
    assert "AI Confidence:* *95.5%*" in msg
    assert "Status:* *Requires immediate verification.*" in msg
    assert "TH-TEST85" in msg
    assert "22.8046°N, 86.1850°E" in msg


def test_get_whatsapp_web_url():
    alert = _sample_alert()
    url = get_whatsapp_web_url(alert, "9967541336")
    assert url.startswith("https://wa.me/919967541336?text=")
    assert "HIGH-RISK" in url or "HIGH-RISK" in url.replace("%20", " ")


def test_send_whatsapp_alert_below_threshold_skipped():
    low_alert = _sample_alert(risk_score=84.4)
    res = send_whatsapp_alert(low_alert, phone="9967541336", threshold=85.0, force=False)
    assert res["status"] == "skipped"
    assert "below alert threshold" in res["reason"]


def test_send_whatsapp_alert_at_or_above_threshold_delivered():
    exact_alert = _sample_alert(risk_score=85.0)
    res = send_whatsapp_alert(exact_alert, phone="9967541336", threshold=85.0, provider="simulated")
    assert res["status"] == "simulated"
    assert res["recipient"] == "+919967541336"
    assert res["risk_score"] == 85.0
    assert "wa_url" in res

    high_alert = _sample_alert(risk_score=92.0)
    res_high = send_whatsapp_alert(high_alert, phone="9967541336", threshold=85.0, provider="simulated")
    assert res_high["status"] == "simulated"
    assert res_high["risk_score"] == 92.0


def test_send_whatsapp_alert_force_bypass_threshold():
    low_alert = _sample_alert(risk_score=40.0)
    res = send_whatsapp_alert(low_alert, phone="9967541336", threshold=85.0, force=True, provider="simulated")
    assert res["status"] == "simulated"


def test_send_batch_whatsapp_alerts():
    alerts = [
        _sample_alert(event_id="TH-1", risk_score=82.0),
        _sample_alert(event_id="TH-2", risk_score=85.0),
        _sample_alert(event_id="TH-3", risk_score=91.5),
        _sample_alert(event_id="TH-4", risk_score=60.0),
    ]
    results = send_batch_whatsapp_alerts(alerts, phone="9967541336", threshold=85.0, provider="simulated")
    assert len(results) == 2
    dispatched_ids = [r["event_id"] for r in results]
    assert "TH-2" in dispatched_ids
    assert "TH-3" in dispatched_ids
    assert "TH-1" not in dispatched_ids
    assert "TH-4" not in dispatched_ids
