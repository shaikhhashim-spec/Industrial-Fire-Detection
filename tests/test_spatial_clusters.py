import pandas as pd

from src.processing.spatial_clusters import find_spatial_clusters


def _cluster_df(rows):
    df = pd.DataFrame(rows)
    df["detection_count"] = df.get("detection_count", 5)
    df["risk_score"] = df.get("risk_score", 50)
    return df


def test_empty_dataframe():
    out, summary = find_spatial_clusters(pd.DataFrame())
    assert out.empty
    assert summary.empty


def test_two_nearby_events_form_one_cluster():
    df = _cluster_df([
        {"grid_cell": "a", "latitude": 22.800, "longitude": 86.180},
        {"grid_cell": "b", "latitude": 22.801, "longitude": 86.181},
    ])
    out, summary = find_spatial_clusters(df, eps_km=2.0, min_samples=2)
    assert (out["spatial_cluster_id"] >= 0).all()
    assert len(summary) == 1
    assert summary.iloc[0]["n_events"] == 2


def test_far_apart_events_stay_unclustered():
    df = _cluster_df([
        {"grid_cell": "a", "latitude": 22.80, "longitude": 86.18},
        {"grid_cell": "b", "latitude": 25.00, "longitude": 90.00},
    ])
    out, summary = find_spatial_clusters(df, eps_km=2.0, min_samples=2)
    assert (out["spatial_cluster_id"] == -1).all()
    assert summary.empty


def test_below_min_samples_returns_no_clusters():
    df = _cluster_df([{"grid_cell": "a", "latitude": 22.80, "longitude": 86.18}])
    out, summary = find_spatial_clusters(df, min_samples=2)
    assert (out["spatial_cluster_id"] == -1).all()
    assert summary.empty
