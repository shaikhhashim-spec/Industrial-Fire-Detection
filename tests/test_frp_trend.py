import pandas as pd

from src.risk.anomaly import (
    TREND_COOLING,
    TREND_ESCALATING,
    TREND_INSUFFICIENT,
    TREND_STABLE,
    compute_frp_trend,
)


def _history(dates_frps, cell="22.8_86.18"):
    dates, frps = zip(*dates_frps, strict=True)
    return pd.DataFrame({"grid_cell": [cell] * len(frps), "acq_date": list(dates), "frp": list(frps)})


def _days(start, frps, step_days=1):
    start = pd.Timestamp(start)
    return [(start + pd.Timedelta(days=i * step_days), frp) for i, frp in enumerate(frps)]


def test_empty_dataframe_returns_empty():
    assert compute_frp_trend(pd.DataFrame()).empty


def test_missing_columns_returns_empty_gracefully():
    df = pd.DataFrame({"grid_cell": ["a"], "acq_date": [pd.Timestamp("2026-08-01")]})
    assert compute_frp_trend(df).empty


def test_no_baseline_before_recent_window_is_insufficient():
    # Only 2 days of history total, both inside the 3-day recent window --
    # nothing older to compare against.
    out = compute_frp_trend(_history(_days("2026-08-01", [5.0, 5.2])))
    row = out.iloc[0]
    assert row["trend_direction"] == TREND_INSUFFICIENT
    assert not row["has_trend_baseline"]


def test_escalating_when_recent_mean_up_sharply():
    # 10 days of a steady baseline (~5 MW), then the most recent 3 days
    # spike to ~10 MW -- a sustained, not single-point, increase.
    baseline = _days("2026-08-01", [5.0] * 10)
    recent = _days("2026-08-11", [10.0, 10.0, 10.0])
    out = compute_frp_trend(_history(baseline + recent))
    row = out.iloc[0]
    assert row["trend_direction"] == TREND_ESCALATING
    assert row["trend_change_pct"] > 25.0


def test_cooling_down_when_recent_mean_drops_sharply():
    baseline = _days("2026-08-01", [10.0] * 10)
    recent = _days("2026-08-11", [3.0, 3.0, 3.0])
    out = compute_frp_trend(_history(baseline + recent))
    row = out.iloc[0]
    assert row["trend_direction"] == TREND_COOLING
    assert row["trend_change_pct"] < -25.0


def test_stable_when_within_threshold():
    baseline = _days("2026-08-01", [5.0] * 10)
    recent = _days("2026-08-11", [5.5, 5.4, 5.3])
    out = compute_frp_trend(_history(baseline + recent))
    row = out.iloc[0]
    assert row["trend_direction"] == TREND_STABLE
    assert -25.0 < row["trend_change_pct"] < 25.0


def test_two_cells_scored_independently():
    escalating = _days("2026-08-01", [5.0] * 10) + _days("2026-08-11", [12.0, 12.0, 12.0])
    stable = _days("2026-08-01", [5.0] * 10) + _days("2026-08-11", [5.1, 4.9, 5.0])
    df = pd.concat([_history(escalating, cell="a"), _history(stable, cell="b")], ignore_index=True)
    out = compute_frp_trend(df)
    assert out[out["grid_cell"] == "a"].iloc[0]["trend_direction"] == TREND_ESCALATING
    assert out[out["grid_cell"] == "b"].iloc[0]["trend_direction"] == TREND_STABLE
