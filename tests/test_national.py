import pandas as pd

from src.national.states import assign_state
from src.national.pipeline import _national_risk
from src.processing.cleaning import clean_hotspots


def test_assign_state_tags_known_coordinates():
    df = pd.DataFrame({
        "latitude": [23.7500, 22.2200],   # Jharia (Jharkhand), Rourkela (Odisha)
        "longitude": [86.4100, 84.8600],
    })
    out = assign_state(df)
    assert out.loc[0, "state"] == "Jharkhand"
    assert out.loc[1, "state"] == "Odisha"


def test_assign_state_empty_dataframe():
    out = assign_state(pd.DataFrame())
    assert out.empty
    assert "state" in out.columns


def test_assign_state_offshore_point_gets_none():
    df = pd.DataFrame({"latitude": [15.0], "longitude": [70.0]})  # open ocean, west of Goa
    out = assign_state(df)
    assert pd.isna(out.loc[0, "state"])


def test_national_risk_bounded_and_labeled():
    df = pd.DataFrame({"persistence_days": [2, 0], "frp": [20.0, 0.5], "confidence_numeric": [90.0, 10.0]})
    out = _national_risk(df)
    assert out["risk_score"].between(0, 100).all()
    assert set(out["risk_level"]) <= {"LOW", "MODERATE", "HIGH", "CRITICAL"}


def test_cleaning_skips_bbox_filter_when_empty_dict():
    # A point far outside the regional bbox but within a broad India range
    row = dict(latitude=28.6, longitude=77.2, acq_date="2026-08-01", acq_time=130,
               frp=5.0, confidence="h", satellite="N")  # Delhi
    out_regional, _ = clean_hotspots(pd.DataFrame([row]))
    assert out_regional.empty  # dropped by the default Jharkhand-Odisha bbox

    out_national, _ = clean_hotspots(pd.DataFrame([row]), bbox={})
    assert len(out_national) == 1  # kept when the bbox filter is skipped
