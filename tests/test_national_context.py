import pandas as pd
import pytest

from src.national import context


@pytest.fixture(autouse=True)
def _reference(monkeypatch):
    """A two-site facility layer and one town, instead of the national build."""
    facilities = pd.DataFrame([
        dict(lat=22.80, lon=86.20, name="Test Steel Works", kind="steel / iron works", detail="steel",
             operator="", capacity_mw=None, source="OpenStreetMap", ref="way/1",
             url="https://www.openstreetmap.org/way/1"),
        dict(lat=22.80, lon=86.21, name="Generic Works", kind="industrial works", detail="works",
             operator="", capacity_mw=None, source="OpenStreetMap", ref="way/2",
             url="https://www.openstreetmap.org/way/2"),
    ])
    facilities["priority"] = facilities["kind"].map({k: i for i, k in enumerate(context.KIND_PRIORITY)})
    places = pd.DataFrame([dict(name="Testpur", lat=22.78, lon=86.18, population=100000,
                                state="Jharkhand", district="Test District")])
    monkeypatch.setattr(context, "_facilities", lambda: facilities)
    monkeypatch.setattr(context, "_places", lambda: places)


def _events(**overrides):
    base = dict(grid_cell="c1", state="Jharkhand", latitude=22.801, longitude=86.201, observation_count=12,
                avg_frp=10.0, max_frp=20.0, avg_confidence=80.0, persistence_days=9, is_persistent=True,
                risk_score=70.0, risk_level="HIGH", satellites=["N20"], event_id="TH-TEST")
    base.update(overrides)
    return pd.DataFrame([base])


def _detail(cell="c1", days=9, night=True, conf="n", frp=20.0, lat=22.801, lon=86.201):
    return pd.DataFrame([
        dict(grid_cell=cell, latitude=lat, longitude=lon, acq_date=pd.Timestamp("2026-09-01") + pd.Timedelta(days=d),
             daynight="N" if night and d == 0 else "D", confidence=conf, confidence_numeric=60.0,
             frp=frp, satellite="N")
        for d in range(days)
    ])


def test_persistent_heat_at_steel_works_is_industrial_activity():
    out = context.enrich_events(_events(), _detail()).iloc[0]
    assert out["category"] == "Persistent Industrial Activity"
    # the steel works wins over the equally close generic works
    assert out["facility"]["name"] == "Test Steel Works"
    assert out["facility"]["distanceKm"] < 1
    assert out["corroborated"]
    assert out["district"] == "Test District"
    assert any("Test Steel Works" in r for r in out["reasons"])
    assert any("rules out sun glint" in r for r in out["reasons"])
    assert out["evidence"]["satellites"] == ["S-NPP"]  # FIRMS "N" is Suomi NPP


def test_isolated_single_detection_is_unconfirmed():
    ev = _events(latitude=25.0, longitude=80.0, is_persistent=False, persistence_days=1, observation_count=1)
    out = context.enrich_events(ev, _detail(days=1, night=False, frp=1.5, lat=25.0, lon=80.0)).iloc[0]
    assert out["facility"] is None
    assert out["category"] == "Requires Verification"
    assert not out["corroborated"]
    assert any(r.startswith("Unconfirmed") for r in out["reasons"])


def test_single_low_confidence_daytime_pixel_is_flagged_false_positive():
    ev = _events(latitude=25.0, longitude=80.0, is_persistent=False, persistence_days=1, observation_count=1)
    detail = _detail(days=1, night=False, conf="l", frp=1.0, lat=25.0, lon=80.0)
    out = context.enrich_events(ev, detail).iloc[0]
    assert out["category"] == "Sun Glint / False Positive"
    assert not out["corroborated"]
