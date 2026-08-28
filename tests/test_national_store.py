import pandas as pd
import pytest

from src.national import store as national_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(national_store, "DB_PATH", tmp_path / "national_test.db")
    yield


def _row(**overrides):
    base = dict(latitude=22.8, longitude=86.18, acq_date="2026-08-01", acq_time=130,
                satellite="N20", instrument="VIIRS", confidence="h", confidence_numeric=90.0,
                frp=5.0, daynight="D", source="VIIRS_NOAA20_NRT", state="Jharkhand")
    base.update(overrides)
    return base


def test_empty_store_returns_empty_history():
    assert national_store.load_history().empty
    assert national_store.count() == 0
    assert national_store.days_covered() == 0


def test_upsert_and_load_roundtrip():
    df = pd.DataFrame([_row()])
    national_store.upsert(df)
    history = national_store.load_history()
    assert len(history) == 1
    assert national_store.count() == 1
    assert history.iloc[0]["state"] == "Jharkhand"


def test_upsert_dedupes_on_natural_key():
    df = pd.DataFrame([_row(frp=5.0), _row(frp=999.0)])  # same natural key, second should win
    national_store.upsert(df)
    history = national_store.load_history()
    assert len(history) == 1
    assert history.iloc[0]["frp"] == 999.0


def test_upsert_across_two_calls_accumulates():
    national_store.upsert(pd.DataFrame([_row(acq_date="2026-08-01")]))
    national_store.upsert(pd.DataFrame([_row(acq_date="2026-08-02")]))
    history = national_store.load_history()
    assert len(history) == 2
    assert national_store.days_covered() == 2


def test_load_history_respects_days_window():
    national_store.upsert(pd.DataFrame([
        _row(acq_date="2026-08-01"), _row(acq_date="2026-08-20"), _row(acq_date="2026-08-28"),
    ]))
    recent = national_store.load_history(days=5)
    assert len(recent) == 1
    assert recent.iloc[0]["acq_date"] == pd.Timestamp("2026-08-28")
