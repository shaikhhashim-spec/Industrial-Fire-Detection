import gzip
import io
import json
import os
import time
import zipfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

import config
from src.firms import fetch
from src.planetary.context import enrich_context, load_references, refresh_geonames_reference
from src.planetary.export import export_global_payload
from src.planetary.pipeline import _select_events, build_global_payload, enrich_weather
from src.utils.spread import calculate_spread_potential


def csv_body():
    now = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5)
    return ("latitude,longitude,acq_date,acq_time,frp,confidence,satellite,bright_ti4,daynight\n"
            f"-3,-60,{now.date()},{now.strftime('%H%M')},50,h,N,340,N\n")


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "GLOBAL_WRI_PATH", tmp_path / "wri.csv")
    monkeypatch.setattr(config, "GLOBAL_PLACES_PATH", tmp_path / "cities15000.txt")
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)


def observations():
    frame = fetch._parse_global_csv(csv_body())
    frame["source"] = "VIIRS_SNPP_NRT"
    frame.attrs.update(source="firms_live", window_hours=24, partial=False, feeds=[])
    return frame


@pytest.mark.parametrize("label,expected", [("low", 30), ("nominal", 60), (" HIGH ", 90)])
def test_public_feed_confidence_words_drive_the_priority_score(label, expected):
    frame = observations()
    frame["confidence"] = label
    event = build_global_payload(frame, weather_limit=0)["events"][0]
    assert event["confidence"] == expected
    assert event["riskScore"] == round(35 + 30 * expected / 100)


def test_global_no_key_and_one_public_download_per_sensor(monkeypatch):
    monkeypatch.setattr(config, "FIRMS_API_KEY", "")
    with patch.object(fetch, "_download_global_csv", return_value=csv_body()) as download:
        frame = fetch.fetch_global_hotspots()
    assert download.call_count == 3
    assert all("Global_24h.csv" in call.args[0] and "/api/" not in call.args[0] for call in download.call_args_list)
    assert all(f["status"] == "live" for f in frame.attrs["feeds"])
    # Exact same observation returned twice is deduplicated without merging other satellites.
    assert len(frame) == 1


def test_cache_ttl_and_stale_source_metadata():
    with patch.object(fetch, "_download_global_csv", return_value=csv_body()):
        fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])
    cache = next(config.CACHE_DIR.glob("*.csv"))
    with patch.object(fetch, "_download_global_csv") as download:
        frame = fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])
    download.assert_not_called()
    assert frame.attrs["feeds"][0]["status"] == "cache"
    old = time.time() - 7 * 3600
    os.utime(cache, (old, old))
    with patch.object(fetch, "_download_global_csv", side_effect=requests.ConnectionError("offline")):
        frame = fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])
    assert frame.attrs["partial"]
    assert frame.attrs["feeds"][0]["status"] == "stale_cache"
    assert frame.attrs["feeds"][0]["cacheAgeHours"] >= 7


def test_overage_cache_never_substitutes_for_live():
    with patch.object(fetch, "_download_global_csv", return_value=csv_body()):
        fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])
    cache = next(config.CACHE_DIR.glob("*.csv"))
    old = time.time() - 25 * 3600
    os.utime(cache, (old, old))
    with patch.object(fetch, "_download_global_csv", side_effect=requests.ConnectionError("offline")):
        with pytest.raises(fetch.FirmsAPIError):
            fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])


def test_malformed_response_preserves_valid_cache():
    with patch.object(fetch, "_download_global_csv", return_value=csv_body()):
        fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])
    cache = next(config.CACHE_DIR.glob("*.csv"))
    original = cache.read_bytes()
    with patch.object(fetch, "_download_global_csv", return_value="<html>error</html>"):
        frame = fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"], force=True)
    assert cache.read_bytes() == original
    assert frame.attrs["feeds"][0]["status"] == "stale_cache"


def test_failed_sensor_is_reported_without_hiding_success():
    with patch.object(fetch, "_download_global_csv", side_effect=[csv_body(), requests.ConnectionError("offline"), requests.ConnectionError("offline")]):
        frame = fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT", "VIIRS_NOAA21_NRT"])
    assert len(frame) == 1
    assert frame.attrs["partial"]
    assert frame.attrs["feeds"][1]["status"] == "unavailable"


def test_cache_write_failure_falls_back_with_correct_provenance():
    with patch.object(fetch, "_download_global_csv", return_value=csv_body()):
        fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"])
    with patch.object(fetch, "_download_global_csv", return_value=csv_body()), \
            patch.object(fetch, "_atomic_cache_text", side_effect=OSError("disk unavailable")):
        frame = fetch.fetch_global_hotspots(["VIIRS_SNPP_NRT"], force=True)
    assert frame.attrs["partial"]
    assert frame.attrs["feeds"][0]["status"] == "stale_cache"


@pytest.mark.parametrize("hours,sources", [(7, None), (24, []), (24, ["FAKE"]), (24, ["../escape"])])
def test_bad_feed_options_fail_before_network(hours, sources):
    with patch.object(fetch, "_download_global_csv") as download:
        with pytest.raises(ValueError):
            fetch.fetch_global_hotspots(sources, hours)
    download.assert_not_called()


def test_streaming_download_enforces_decoded_byte_limit(monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_FIRMS_MAX_BYTES", 3)
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = iter([b"12", b"34"])
    with patch.object(fetch.requests, "get", return_value=response):
        with pytest.raises(fetch.FirmsAPIError, match="byte limit"):
            fetch._download_global_csv("https://example.invalid/data.csv")


def test_global_payload_keeps_southern_hemisphere_and_honest_unknown_context():
    payload = build_global_payload(observations(), weather_limit=0)
    event = payload["events"][0]
    assert event["latitude"] == -3 and event["longitude"] == -60
    assert event["region"] == "South America"
    assert event["country"] is None
    assert event["category"] == "Requires Verification"
    assert event["confidence"] == 90
    assert "plume" not in event and "spreadPotential" not in event
    assert payload["meta"]["scope"] == "global"
    assert payload["meta"]["windowDays"] == 1
    assert payload["meta"]["context"]["facilities"] == "unavailable"
    json.dumps(payload, allow_nan=False)


def test_global_snapshot_does_not_reuse_old_observations():
    frame = observations()
    frame["acq_date"] = "2000-01-01"
    with pytest.raises(RuntimeError, match="rolling window"):
        build_global_payload(frame, weather_limit=0)


def test_invalid_frp_or_hhmm_rows_do_not_break_other_valid_observations():
    good = observations()
    invalid = pd.concat([good] * 4, ignore_index=True)
    invalid["longitude"] = [1, 2, 3, 4]
    invalid["acq_time"] = [float("inf"), 1260, 1250.5, 2359]
    invalid["frp"] = [1, 1, 1, float("inf")]
    raw = pd.concat([good, invalid], ignore_index=True)
    payload = build_global_payload(raw, weather_limit=0)
    assert len(payload["events"]) == 1
    assert payload["meta"]["cleaning"]["dropped_invalid_frp_or_time"] == 4


def test_invalid_reference_cannot_break_the_detection_export():
    config.GLOBAL_WRI_PATH.write_text("latitude,longitude\n1,2\n", encoding="utf-8")
    payload = build_global_payload(observations(), weather_limit=0)
    assert len(payload["events"]) == 1
    assert "invalid WRI" in payload["meta"]["context"]["facilities"]


def test_sampling_is_bounded_and_metrics_count_all_cells():
    frame = observations()
    second = frame.copy()
    second["latitude"], second["longitude"] = 55, -100
    raw = pd.concat([frame, second], ignore_index=True)
    raw.attrs = dict(frame.attrs)
    payload = build_global_payload(raw, max_events=1, weather_limit=0)
    assert payload["meta"]["globalActiveHotspots"] == 2
    assert payload["meta"]["events"] == 1
    assert payload["meta"]["omittedEvents"] == 1
    assert payload["meta"]["partial"]
    assert payload["meta"]["totalGlobalFrpGw"] == .1


def test_vectorized_evidence_keeps_peak_latest_and_all_sensor_history():
    records = []
    now = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5)
    for hours, source, satellite, frp, confidence, brightness, daynight in [
        (23, "VIIRS_SNPP_NRT", "N", 50, "h", 340, "N"),
        (1, "VIIRS_NOAA20_NRT", "N20", 7, "n", 310, "D"),
        (0, "VIIRS_NOAA21_NRT", "N21", 3, "l", 280, "N"),
    ]:
        stamp = now - pd.Timedelta(hours=hours)
        records.append(dict(latitude=-3, longitude=-60, source=source, satellite=satellite, frp=frp,
                            confidence=confidence, bright_ti4=brightness, daynight=daynight,
                            acq_date=str(stamp.date()), acq_time=stamp.strftime("%H%M")))
    raw = pd.DataFrame(records)
    event = build_global_payload(raw, weather_limit=0)["events"][0]
    assert event["detectionCount"] == 3
    assert event["frp"] == 50 and event["brightness"] == 340
    assert event["confidence"] == 60 and event["riskScore"] == 53
    assert event["satellite"] == "VIIRS NOAA-21"
    assert len(event["satellites"]) == 3
    assert event["evidence"]["meanFrp"] == 20
    assert event["evidence"]["nightPasses"] == 2
    assert event["evidence"]["lowConfidenceShare"] == .333
    assert event["persistenceDays"] == raw.acq_date.nunique()
    assert {day["date"] for day in event["history"]} == set(raw.acq_date)


def test_weather_deadline_stops_new_requests_and_reports_coverage():
    events = [{"frp": 100, "latitude": 1, "longitude": 2}, {"frp": 50, "latitude": 3, "longitude": 4}]
    provider = MagicMock(return_value={"speed_kmh": 20, "direction_deg": 90, "source": "open-meteo"})
    with patch("src.planetary.pipeline.time.monotonic", side_effect=[0, 0, 100]):
        meta = enrich_weather(events, provider, 2)
    provider.assert_called_once()
    assert meta["weatherAttemptedEvents"] == 1
    assert meta["weatherDeadlineExceeded"]


def test_sampling_prefers_geographic_diversity_then_fills_by_priority():
    events = [{"id": "a", "latitude": 1.1, "longitude": 1.1, "riskScore": 90, "frp": 50},
              {"id": "b", "latitude": 1.2, "longitude": 1.2, "riskScore": 80, "frp": 40},
              {"id": "c", "latitude": -30, "longitude": 140, "riskScore": 20, "frp": 10}]
    assert {e["id"] for e in _select_events(events, 2)} == {"a", "c"}


def test_wri_nearby_does_not_invent_country_or_industrial_fire():
    event = build_global_payload(observations(), weather_limit=0)["events"][0]
    facilities = pd.DataFrame([{"latitude": -3, "longitude": -60, "name": "Mapped plant", "primary_fuel": "Gas", "gppd_idnr": "WRI1", "country": "BRA"}])
    enrich_context([event], facilities, pd.DataFrame())
    assert event["facility"]["distanceKm"] == 0
    assert event["country"] is None
    assert event["category"] == "Requires Verification"
    assert event["facility"]["capacityMw"] is None


def test_global_reference_excludes_renewable_plants_and_invalid_coordinates():
    pd.DataFrame([
        {"latitude": -3, "longitude": -60, "name": "Gas", "primary_fuel": "Gas", "gppd_idnr": "1"},
        {"latitude": -3, "longitude": -60, "name": "Wind", "primary_fuel": "Wind", "gppd_idnr": "2"},
        {"latitude": 999, "longitude": -60, "name": "Bad", "primary_fuel": "Gas", "gppd_idnr": "3"},
    ]).to_csv(config.GLOBAL_WRI_PATH, index=False)
    facilities, _, _ = load_references()
    assert facilities.name.tolist() == ["Gas"]


def test_weather_budget_source_and_spread_score():
    events = [{"frp": 100, "latitude": 1, "longitude": 2}, {"frp": 50, "latitude": 4, "longitude": 5}]
    provider = MagicMock(return_value={"speed_kmh": 60, "direction_deg": 90, "source": "open-meteo", "observed_at": "2026-10-03T12:00:00Z",
                                      "relative_humidity_2m": 0, "temperature_2m": 40, "precipitation": 0})
    meta = enrich_weather(events, provider, 1)
    provider.assert_called_once_with(1, 2)
    assert meta["weatherEnrichedEvents"] == 1
    assert meta["weatherEligibleEvents"] == 2
    assert events[0]["plume"]["downwindBearingDeg"] == 270
    assert events[0]["plume"]["estimated"]
    assert events[0]["spreadPotential"]["score"] == 100
    assert events[0]["spreadPotential"]["label"] == "HIGH"
    assert "not official FWI" in events[0]["spreadPotential"]["caveat"]
    assert "plume" not in events[1]


def test_global_spread_uses_shared_scorer_exactly():
    weather = {"speed_kmh": 25, "direction_deg": 45, "source": "open-meteo", "humidity_pct": 32,
               "temperature_c": 28, "precipitation_mm": 2}
    event = {"frp": 42, "latitude": 1, "longitude": 2}
    enrich_weather([event], lambda *_: weather, 1)
    assert event["spreadPotential"] == calculate_spread_potential(weather, 42)


def geonames_zip(member="cities15000.txt", body=None):
    fields = ["1", "Real city", "Real city", "", "-3", "-60", "P", "PPL", "BR", "", "", "", "", "", "20000", "", "", "UTC", "2026-01-01"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, body if body is not None else "\t".join(fields) + "\n")
    return buffer.getvalue()


def mock_zip_response(body):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = iter([body])
    return response


def test_geonames_download_validates_zip_and_city_table():
    with patch("src.planetary.context.requests.get", return_value=mock_zip_response(geonames_zip())):
        refresh_geonames_reference()
    _, places, status = load_references()
    assert places.name.tolist() == ["Real city"]
    assert "1 cities" in status["places"]
    event = build_global_payload(observations(), weather_limit=0)["events"][0]
    assert event["place"]["name"] == "Real city"
    assert event["country"] is None


@pytest.mark.parametrize("archive", [geonames_zip("../cities15000.txt"), geonames_zip(body="invalid"), b"not a zip"])
def test_bad_geonames_zip_preserves_previous_reference(archive):
    config.GLOBAL_PLACES_PATH.write_text("previous", encoding="utf-8")
    with patch("src.planetary.context.requests.get", return_value=mock_zip_response(archive)):
        with pytest.raises((ValueError, zipfile.BadZipFile)):
            refresh_geonames_reference()
    assert config.GLOBAL_PLACES_PATH.read_text() == "previous"


def test_offline_weather_creates_neither_plume_nor_score():
    event = {"frp": 100, "latitude": 1, "longitude": 2}
    meta = enrich_weather([event], lambda *_: {"speed_kmh": 12, "direction_deg": 180, "source": "offline_fallback"}, 1)
    assert meta["weatherEnrichedEvents"] == 0
    assert "plume" not in event and "spreadPotential" not in event


def test_stale_wind_is_labeled_and_never_produces_spread_score():
    event = {"frp": 100, "latitude": 1, "longitude": 179.9999}
    enrich_weather([event], lambda *_: {"speed_kmh": 60, "direction_deg": 270, "source": "stale_cache",
                                      "relative_humidity_2m": 1, "temperature_2m": 40, "precipitation": 0}, 1)
    assert event["plume"]["source"] == "stale_cache"
    assert all(-180 <= point[0] <= 180 for point in event["plume"]["polygon"])
    assert "spreadPotential" not in event


def test_compact_atomic_export_keeps_india_and_roundtrips_gzip(tmp_path):
    india = tmp_path / "events.json"
    india.write_text("national", encoding="utf-8")
    payload = build_global_payload(observations(), weather_limit=0)
    path = export_global_payload(payload, tmp_path / "global-events.json")
    assert india.read_text() == "national"
    assert json.loads(path.read_text())["meta"]["scope"] == "global"
    assert gzip.decompress(path.with_suffix(".json.gz").read_bytes()) == path.read_bytes()
    assert (tmp_path / "global-facilities.geojson").exists()
    with pytest.raises(ValueError, match="national"):
        export_global_payload(payload, india)


def test_invalid_json_does_not_replace_existing_export(tmp_path):
    path = tmp_path / "global-events.json"
    path.write_text("previous", encoding="utf-8")
    with pytest.raises(ValueError):
        export_global_payload({"meta": {}, "events": [{"frp": float("nan")}]}, path)
    assert path.read_text() == "previous"
