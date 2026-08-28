import pandas as pd

import config
from src.alerts.engine import generate_alerts


def _cluster_row(**overrides):
    base = dict(grid_cell="22.8_86.18", latitude=22.8, longitude=86.18,
                dominant_label="Likely Industrial Fire", risk_score=10, risk_level="LOW",
                is_persistent=False, avg_frp=1.0, max_frp=1.0,
                industrial_distance_km=0.1, status="RECURRING")
    base[f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"] = 1
    base.update(overrides)
    return base


def _detail_df():
    return pd.DataFrame({
        "grid_cell": ["22.8_86.18"],
        "acq_date": [pd.Timestamp("2026-08-28")],
    })


def test_empty_cluster_df_returns_no_alerts():
    assert generate_alerts(_detail_df(), pd.DataFrame()) == []


def test_critical_risk_generates_critical_alert():
    cluster_df = pd.DataFrame([_cluster_row(risk_score=90, risk_level="CRITICAL")])
    alerts = generate_alerts(_detail_df(), cluster_df)
    assert any(a["type"] == "critical_risk" for a in alerts)
    assert alerts[0]["severity"] == "CRITICAL"


def test_high_risk_requires_persistence():
    non_persistent = pd.DataFrame([_cluster_row(risk_score=60, risk_level="HIGH", is_persistent=False)])
    assert not any(a["type"] == "high_risk_persistent" for a in generate_alerts(_detail_df(), non_persistent))

    persistent = pd.DataFrame([_cluster_row(risk_score=60, risk_level="HIGH", is_persistent=True)])
    assert any(a["type"] == "high_risk_persistent" for a in generate_alerts(_detail_df(), persistent))


def test_frp_spike_detected():
    cluster_df = pd.DataFrame([_cluster_row(avg_frp=2.0, max_frp=2.0 * config.ALERT_FRP_SPIKE_MULTIPLIER + 1,
                                             risk_score=10)])
    alerts = generate_alerts(_detail_df(), cluster_df)
    assert any(a["type"] == "frp_spike" for a in alerts)


def test_alerts_sorted_most_severe_first():
    cluster_df = pd.DataFrame([
        _cluster_row(grid_cell="a", risk_score=60, risk_level="HIGH", is_persistent=True),
        _cluster_row(grid_cell="b", risk_score=90, risk_level="CRITICAL"),
    ])
    alerts = generate_alerts(_detail_df(), cluster_df)
    assert alerts[0]["severity"] == "CRITICAL"
