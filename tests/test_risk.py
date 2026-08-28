import pandas as pd

from src.risk.scoring import compute_risk, risk_level


def _row(**overrides):
    base = dict(persistence_days=0, frp=0.0, confidence_numeric=0.0, zone_type="other",
                industrial_distance_km=10.0, recurrence_frequency=0.0)
    base.update(overrides)
    return base


def test_score_is_bounded_0_100():
    df = pd.DataFrame([_row(persistence_days=999, frp=999, confidence_numeric=999, recurrence_frequency=999)])
    out = compute_risk(df)
    assert 0 <= out.loc[0, "risk_score"] <= 100


def test_low_everything_is_low_risk():
    df = pd.DataFrame([_row()])
    out = compute_risk(df)
    assert out.loc[0, "risk_level"] == "LOW"


def test_high_everything_is_critical():
    df = pd.DataFrame([_row(persistence_days=30, frp=20, confidence_numeric=100,
                             zone_type="industrial", recurrence_frequency=1.0)])
    out = compute_risk(df)
    assert out.loc[0, "risk_level"] == "CRITICAL"


def test_risk_level_boundaries():
    assert risk_level(0) == "LOW"
    assert risk_level(25) == "LOW"
    assert risk_level(26) == "MODERATE"
    assert risk_level(50) == "MODERATE"
    assert risk_level(51) == "HIGH"
    assert risk_level(75) == "HIGH"
    assert risk_level(76) == "CRITICAL"
    assert risk_level(100) == "CRITICAL"


def test_empty_dataframe():
    out = compute_risk(pd.DataFrame())
    assert out.empty
    assert "risk_score" in out.columns
