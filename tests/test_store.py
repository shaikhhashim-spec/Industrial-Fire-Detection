import pandas as pd
import pytest

from src import store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "store_test.db")
    yield


def test_dismiss_and_load_roundtrip():
    store.dismiss_alert("TH-000001", "jharkhand_odisha")
    assert store.load_dismissed("jharkhand_odisha") == {"TH-000001"}


def test_dismissed_scoped_by_region():
    store.dismiss_alert("TH-000001", "jharkhand_odisha")
    store.dismiss_alert("TH-000002", "india")
    assert store.load_dismissed("jharkhand_odisha") == {"TH-000001"}
    assert store.load_dismissed("india") == {"TH-000002"}
    assert store.load_dismissed() == {"TH-000001", "TH-000002"}


def test_dismiss_is_idempotent():
    store.dismiss_alert("TH-000001", "jharkhand_odisha")
    store.dismiss_alert("TH-000001", "jharkhand_odisha")
    assert store.load_dismissed("jharkhand_odisha") == {"TH-000001"}


def test_restore_alert_removes_only_that_region():
    store.dismiss_alert("TH-000001", "jharkhand_odisha")
    store.dismiss_alert("TH-000001", "india")

    store.restore_alert("TH-000001", "jharkhand_odisha")

    assert store.load_dismissed("jharkhand_odisha") == set()
    assert store.load_dismissed("india") == {"TH-000001"}


def test_empty_store_has_no_dismissed():
    assert store.load_dismissed() == set()
    assert store.load_dismissed("jharkhand_odisha") == set()


@pytest.mark.parametrize("dtype", [object, "boolean", "Float64"])
@pytest.mark.parametrize("column", ["in_agricultural_zone", "is_persistent"])
def test_nullable_boolean_membership_roundtrip_keeps_unknown_null(dtype, column):
    raw = pd.DataFrame([dict(latitude=22.8, longitude=86.18, acq_date=f"2026-10-0{i + 1}",
                             acq_time=130, satellite="N20", source="live") for i in range(3)])
    raw[column] = pd.Series([None, False, True], dtype=dtype)
    store.upsert(raw)
    history = store.load_all().sort_values("acq_date").reset_index(drop=True)
    assert pd.isna(history.loc[0, column])
    assert history.loc[1, column] == 0
    assert history.loc[2, column] == 1
    store.upsert(history)
    with store._connect() as connection:
        values = connection.execute(f"SELECT {column} FROM hotspots ORDER BY acq_date").fetchall()
    assert values == [(None,), (0.0,), (1.0,)]
