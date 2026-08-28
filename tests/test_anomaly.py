import pandas as pd

from src.risk.anomaly import compute_frp_anomaly


def _history(frps, cell="22.8_86.18"):
    return pd.DataFrame({
        "grid_cell": [cell] * len(frps),
        "acq_date": [pd.Timestamp("2026-08-01") + pd.Timedelta(days=i) for i in range(len(frps))],
        "frp": frps,
    })


def test_empty_dataframe_returns_empty():
    out = compute_frp_anomaly(pd.DataFrame())
    assert out.empty


def test_insufficient_history_has_no_baseline():
    out = compute_frp_anomaly(_history([3.0]))
    row = out.iloc[0]
    assert not row["has_baseline"]
    assert not row["is_anomalous"]


def test_stable_frp_is_not_anomalous():
    out = compute_frp_anomaly(_history([5.0, 5.1, 4.9, 5.0, 5.0]))
    row = out.iloc[0]
    assert row["has_baseline"]
    assert not row["is_anomalous"]


def test_sudden_spike_is_anomalous():
    out = compute_frp_anomaly(_history([5.0, 5.1, 4.9, 5.0, 42.0]))
    row = out.iloc[0]
    assert row["has_baseline"]
    assert row["is_anomalous"]
    assert row["latest_frp"] == 42.0
    assert row["frp_change_pct"] > 0


def test_two_cells_scored_independently():
    a = _history([5.0, 5.0, 5.0, 40.0], cell="a")
    b = _history([2.0, 2.1, 1.9, 2.0], cell="b")
    out = compute_frp_anomaly(pd.concat([a, b], ignore_index=True))
    a_row = out[out["grid_cell"] == "a"].iloc[0]
    b_row = out[out["grid_cell"] == "b"].iloc[0]
    assert a_row["is_anomalous"]
    assert not b_row["is_anomalous"]


def test_missing_frp_column_returns_empty_gracefully():
    df = pd.DataFrame({"grid_cell": ["a"], "acq_date": [pd.Timestamp("2026-08-01")]})
    out = compute_frp_anomaly(df)
    assert out.empty
