import pandas as pd

from src.processing.persistence import build_cluster_summary, compute_persistence


def _detections(n_days, lat=22.80, lon=86.18, frp=5.0):
    today = pd.Timestamp("2026-08-28")
    return pd.DataFrame({
        "latitude": [lat] * n_days,
        "longitude": [lon] * n_days,
        "acq_date": [today - pd.Timedelta(days=i) for i in range(n_days)],
        "frp": [frp] * n_days,
        "confidence_numeric": [80] * n_days,
    })


def test_persistent_flag_true_at_or_above_threshold():
    df = compute_persistence(_detections(5), min_days=5)
    assert df["is_persistent"].all()


def test_persistent_flag_false_below_threshold():
    df = compute_persistence(_detections(4), min_days=5)
    assert not df["is_persistent"].any()


def test_empty_dataframe_cluster_summary():
    out = build_cluster_summary(pd.DataFrame())
    assert out.empty


def test_cluster_summary_aggregates():
    df = _detections(6, frp=3.0)
    df.loc[0, "frp"] = 9.0  # one spike
    summary = build_cluster_summary(df, min_days=5)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["detection_count"] == 6
    assert row["max_frp"] == 9.0
    assert row["is_persistent"]


def test_two_cells_stay_separate():
    a = _detections(6, lat=22.80, lon=86.18)
    b = _detections(2, lat=23.75, lon=86.41)
    summary = build_cluster_summary(pd.concat([a, b], ignore_index=True), min_days=5)
    assert len(summary) == 2
    assert summary["is_persistent"].sum() == 1
