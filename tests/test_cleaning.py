import pandas as pd

from src.processing.cleaning import clean_hotspots

GOOD_ROW = dict(latitude=22.80, longitude=86.18, acq_date="2026-08-01", acq_time=130,
                frp=5.0, confidence="h", satellite="N")


def _df(rows):
    return pd.DataFrame(rows)


def test_empty_dataframe():
    out, report = clean_hotspots(pd.DataFrame())
    assert out.empty
    assert report["input_rows"] == 0


def test_drops_missing_coordinates():
    rows = [GOOD_ROW, {**GOOD_ROW, "latitude": None}]
    out, report = clean_hotspots(_df(rows))
    assert len(out) == 1
    assert report["dropped_missing_coords_or_date"] == 1


def test_drops_invalid_coordinates():
    rows = [GOOD_ROW, {**GOOD_ROW, "latitude": 999.0}]
    out, _ = clean_hotspots(_df(rows))
    assert len(out) == 1


def test_drops_outside_bounding_box():
    rows = [GOOD_ROW, {**GOOD_ROW, "latitude": 5.0, "longitude": 5.0}]
    out, report = clean_hotspots(_df(rows))
    assert len(out) == 1
    assert report["dropped_outside_bbox"] == 1


def test_missing_frp_is_filled_not_dropped():
    rows = [{**GOOD_ROW, "frp": None}]
    out, _ = clean_hotspots(_df(rows))
    assert len(out) == 1
    assert out.loc[0, "frp"] == 0.0


def test_duplicates_removed():
    rows = [GOOD_ROW, GOOD_ROW.copy()]
    out, report = clean_hotspots(_df(rows))
    assert len(out) == 1
    assert report["dropped_duplicates"] == 1


def test_bad_dates_dropped():
    rows = [GOOD_ROW, {**GOOD_ROW, "acq_date": "not-a-date"}]
    out, report = clean_hotspots(_df(rows))
    assert len(out) == 1
    assert report["dropped_bad_dates"] == 1
