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


def test_empty_store_has_no_dismissed():
    assert store.load_dismissed() == set()
    assert store.load_dismissed("jharkhand_odisha") == set()
