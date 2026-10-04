"""Export provenance, offline preservation and JS/Python contract parity."""
import copy
import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.planetary.export import export_global_payload
from src.planetary.pipeline import build_global_payload
from src.processing.cleaning import clean_hotspots
from src import store as regional_store
from src.national import store as national_store
from src.utils.export_3d_globe import (
    analyze_thermal_change,
    augment_thermal_snapshot,
    transform_national_to_holo_events,
    transform_regional_to_holo_events,
)

ROOT = Path(__file__).resolve().parents[1]


def observation(day, frp, **extra):
    return dict(date=day, frp=frp, satellite="N20", instrument="VIIRS", daynight="N", **extra)


def event(current=30):
    return {"acqDate": "2026-10-04", "frp": 999, "history": [
        observation("2026-10-01", 10), observation("2026-10-02", 12),
        observation("2026-10-03", 8), observation("2026-10-04", current)]}


def test_js_python_contract_parity():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for cross-language contract parity")
    cases = [None, {}, event(), event(5), event(15), event(14.9), event(10)]
    for extra in [{"frp": None}, {"frp": -1}, {"frp": "30"}, {"synthetic": True},
                  {"frp": 0}, {"frp": 0, "frpObserved": True}, {"frpObserved": False},
                  {"satellite": "MODIS_NRT"}, {"daynight": "D"}, {"instrument": "MODIS"}]:
        e = event()
        e["history"][-1].update(extra)
        cases.append(e)
    for frp in range(0, 301, 7):
        cases.append(event(frp / 10))
    for flags in [{"historyTruncated": True}, {"acqDate": "2026-02-30"}, {"acqDate": "0000-01-01"}]:
        cases.append({**event(), **flags})
    e = event()
    e["history"][0]["date"] = "2026-09-20"
    cases.append(e)
    e = event()
    e["history"].append({**observation("2026-10-04", 50), "satellite": "N21"})
    cases.append(copy.deepcopy(e))
    e["history"] += [{**observation(day, 10), "satellite": "N21"} for day in ["2026-10-01", "2026-10-02", "2026-10-03"]]
    cases.append(e)
    e = event()
    e["history"].append(observation("2026-10-03", None))
    cases.append(e)
    e = event(1e308)
    cases.append(e)
    e["history"] = [{**r, "frp": 1e-300} if r["date"] != e["acqDate"] else r for r in e["history"]]
    cases.append(e)
    e = event()
    e["history"] += [observation("2026-10-01", 1)] * 100
    cases.append(e)
    e = event()
    e["history"] = [{"date": r["date"], "frp": r["frp"]} for r in e["history"]]
    cases.append(e)
    e = event()
    e["history"] = [{**r, "frp": 0} if r["date"] != e["acqDate"] else r for r in e["history"]]
    cases.append(e)
    script = """import { analyzeThermalChange } from './site/thermal-change.mjs';
import { readFileSync } from 'node:fs';
console.log(JSON.stringify(JSON.parse(readFileSync(0, 'utf8')).map(analyzeThermalChange)));"""
    completed = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT,
                               input=json.dumps(cases), text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == [analyze_thermal_change(e) for e in cases]


@pytest.mark.parametrize("regional", [True, False])
def test_cleaner_store_export_excludes_placeholder_baseline_days(tmp_path, monkeypatch, regional):
    store = regional_store if regional else national_store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "history.db")
    rows = [dict(latitude=22.8, longitude=86.18, acq_date=day, acq_time=130,
                 satellite="N20", instrument="VIIRS", confidence="h", frp=frp, daynight="N",
                 source="VIIRS_NOAA20_NRT") for day, frp in
            [("2026-10-01", None), ("2026-10-02", "bad"), ("2026-10-03", 10), ("2026-10-04", 15)]]
    # Include genuine readings on the placeholder days: partial coverage is
    # still unsafe even when a valid lower daily peak remains after filtering.
    rows += [{**rows[0], "frp": 1, "acq_time": 131}, {**rows[1], "frp": 1, "acq_time": 131}]
    clean, _ = clean_hotspots(pd.DataFrame(rows))
    store.upsert(clean)
    history = store.load_input_history() if regional else store.load_history()
    clean_again, _ = clean_hotspots(history)
    assert clean_again["frpObserved"].tolist() == clean["frpObserved"].tolist()
    clean_again["grid_cell"] = "cell"
    summary = pd.DataFrame([dict(grid_cell="cell", max_frp=15, last_detected="2026-10-04")])
    transform = transform_regional_to_holo_events if regional else transform_national_to_holo_events
    exported = transform(clean_again, summary)[0]
    assert exported["thermalChange"]["status"] == "insufficient_history"
    assert exported["thermalChange"]["observationDays"] == 1
    assert exported["thermalChange"]["priorityPoints"] == 0
    assert exported["history"][0]["frp"] is None
    assert exported["history"][0]["frpObserved"] is False


@pytest.mark.parametrize("regional", [True, False])
def test_existing_store_migration_leaves_legacy_zero_unknown(tmp_path, monkeypatch, regional):
    store = regional_store if regional else national_store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "legacy.db")
    table = "hotspots" if regional else "national_hotspots"
    columns = store.ALL_COLUMNS if regional else store.INPUT_COLUMNS
    definitions = ",".join(f"{c} {'TEXT' if c in store._TEXT_COLUMNS else 'REAL'}"
                           for c in columns if c != "frpObserved")
    with sqlite3.connect(store.DB_PATH) as connection:
        connection.execute(f"CREATE TABLE {table} ({definitions}, PRIMARY KEY ({','.join(store.NATURAL_KEY)}))")
        connection.execute(f"INSERT INTO {table} (latitude,longitude,acq_date,acq_time,satellite,source,frp,daynight) "
                           "VALUES (22.8,86.18,'2026-10-04',130,'N20','VIIRS_NOAA20_NRT',0,'N')")
    history = store.load_input_history() if regional else store.load_history()
    assert pd.isna(history.loc[0, "frpObserved"])
    clean, _ = clean_hotspots(history)
    assert not clean.loc[0, "frpObserved"]
    store.upsert(clean)
    history = store.load_input_history() if regional else store.load_history()
    history["grid_cell"] = "cell"
    exported = transform_national_to_holo_events(history, pd.DataFrame([dict(grid_cell="cell")]))[0]
    assert exported["history"][0]["frp"] is None
    assert exported["thermalChange"]["currentFrp"] is None


@pytest.mark.parametrize("regional", [True, False])
def test_measured_zero_survives_cleaner_store_export(tmp_path, monkeypatch, regional):
    store = regional_store if regional else national_store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "zero.db")
    raw = pd.DataFrame([dict(latitude=22.8, longitude=86.18, acq_date="2026-10-04", acq_time=130,
                             satellite="N20", instrument="VIIRS", daynight="N", confidence="h", source="live",
                             frp=0, frpObserved=True)])
    clean, _ = clean_hotspots(raw)
    store.upsert(clean)
    history = store.load_input_history() if regional else store.load_history()
    history["grid_cell"] = "cell"
    exported = transform_national_to_holo_events(history, pd.DataFrame([dict(grid_cell="cell")]))[0]
    assert exported["history"][0]["frp"] == 0
    assert exported["history"][0]["frpObserved"] is True
    assert exported["thermalChange"]["currentFrp"] == 0


def test_legacy_unmarked_zero_is_null_even_without_recleaning():
    detail = pd.DataFrame([dict(grid_cell="cell", acq_date="2026-10-04", frp=0, satellite="N20", daynight="N")])
    exported = transform_national_to_holo_events(detail, pd.DataFrame([dict(grid_cell="cell")]))[0]
    assert exported["history"][0]["frp"] is None
    assert exported["history"][0]["frpObserved"] is None


def test_global_four_days_preserve_sensor_pass_history_and_aggregate_counts(tmp_path):
    rows = []
    now = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)
    for offset in range(4):
        stamp = now - pd.Timedelta(days=offset)
        for sat, source in [("N20", "VIIRS_NOAA20_NRT"), ("N21", "VIIRS_NOAA21_NRT")]:
            for repeat in range(2):
                pass_time = stamp - pd.Timedelta(minutes=repeat)
                rows.append(dict(latitude=22.8, longitude=86.18, acq_date=str(pass_time.date()),
                                 acq_time=int(pass_time.strftime("%H%M")), frp=(30 if offset == 0 else 10) - repeat,
                                 satellite=sat, confidence="h", instrument="VIIRS", daynight="N", source=source))
    raw = pd.DataFrame(rows)
    raw.attrs.update(source="firms_live", window_hours=120, partial=False, feeds=[])
    payload = build_global_payload(raw, weather_limit=0)
    e = payload["events"][0]
    assert len(e["history"]) == 8
    assert e["detectionCount"] == 16
    assert e["persistenceDays"] == 4
    assert all(r["frpObserved"] is True and r["instrument"] == "VIIRS" for r in e["history"])
    assert {r["satellite"] for r in e["history"]} == {"VIIRS NOAA-20", "VIIRS NOAA-21"}
    dest = export_global_payload(payload, tmp_path / "global-events.json")
    analysis = json.loads(dest.read_text())["events"][0]["thermalChange"]
    assert analysis["status"] == "elevated"
    assert analysis["baselineFrp"] == 10
    assert analysis["observationDays"] == 3


def test_global_raw_zero_is_measured_and_existing_false_is_never_promoted():
    stamp = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5)
    raw = pd.DataFrame([dict(latitude=22.8, longitude=86.18, acq_date=str(stamp.date()),
                            acq_time=int(stamp.strftime("%H%M")), frp=0, satellite="N20", instrument="VIIRS",
                            confidence="h", daynight="N", source="VIIRS_NOAA20_NRT")])
    raw.attrs.update(source="firms_live", window_hours=24)
    measured = build_global_payload(raw, weather_limit=0)["events"][0]["history"][0]
    assert measured["frp"] == 0
    assert measured["frpObserved"] is True
    raw["frpObserved"] = False
    unknown = build_global_payload(raw, weather_limit=0)["events"][0]["history"][0]
    assert unknown["frp"] is None
    assert unknown["frpObserved"] is False


def snapshot(day, frp=10, satellite="N20", **extra):
    e = {"id": "GL-stable", "latitude": 22.8, "longitude": 86.18, "acqDate": day,
         "frp": frp, "riskScore": 20, "persistenceDays": 1, "detectionCount": 2,
         "history": [{**observation(day, frp), "satellite": satellite, "frpObserved": True}], **extra}
    return {"meta": {"source": "firms_live", "scope": "global", "observations": 2, "windowDays": 1}, "events": [e]}


def test_daily_snapshot_accumulation_changes_only_history_and_thermal_summary(tmp_path):
    dest = tmp_path / "global-events.json"
    for day, frp in [("2026-10-01", 10), ("2026-10-02", 10), ("2026-10-03", 10), ("2026-10-04", 30)]:
        payload = snapshot(day, frp)
        original = copy.deepcopy(payload)
        export_global_payload(payload, dest)
        assert payload == original
    result = json.loads(dest.read_text())
    e = result["events"][0]
    assert e["thermalChange"]["status"] == "elevated"
    assert e["thermalChange"]["baselineFrp"] == 10
    assert e["thermalChange"]["observationDays"] == 3
    assert e["persistenceDays"] == 1 and e["detectionCount"] == 2 and e["riskScore"] == 20
    assert result["meta"]["observations"] == 2 and result["meta"]["windowDays"] == 1
    assert "selected snapshots" in result["meta"]["historyScope"]
    export_global_payload(payload, dest)
    assert len(json.loads(dest.read_text())["events"][0]["history"]) == 4
    assert gzip.decompress(dest.with_suffix(".json.gz").read_bytes()) == dest.read_bytes()


@pytest.mark.parametrize("change", [{"id": "GL-other"}, {"longitude": 86.2}])
def test_snapshot_history_requires_both_stable_id_and_coordinate_cell(tmp_path, change):
    dest = tmp_path / "global-events.json"
    for day in ["2026-10-01", "2026-10-02", "2026-10-03"]:
        export_global_payload(snapshot(day), dest)
    export_global_payload(snapshot("2026-10-04", 30, **change), dest)
    assert len(json.loads(dest.read_text())["events"][0]["history"]) == 1


def test_snapshot_sensor_change_and_missing_day_are_honest(tmp_path):
    dest = tmp_path / "global-events.json"
    for day in ["2026-09-30", "2026-10-02", "2026-10-03"]:
        export_global_payload(snapshot(day), dest)
    export_global_payload(snapshot("2026-10-04", 10), dest)
    result = json.loads(dest.read_text())["events"][0]["thermalChange"]
    assert result["status"] == "stable" and result["baselineFrp"] == 10 and result["gaps"] == 1
    export_global_payload(snapshot("2026-10-05", 30, satellite="N21"), dest)
    assert json.loads(dest.read_text())["events"][0]["thermalChange"]["status"] == "insufficient_history"


def test_snapshot_excludes_legacy_metadata_and_bounds_history_without_stale_events(tmp_path):
    dest = tmp_path / "global-events.json"
    previous = snapshot("2026-09-01")
    previous["events"][0]["history"] += [{"date": "2026-10-01", "frp": 0}, {"date": "2026-10-02", "frp": 10}]
    previous["events"].append({**previous["events"][0], "id": "GL-old-only"})
    dest.write_text(json.dumps(previous))
    export_global_payload(snapshot("2026-10-04", 30), dest)
    result = json.loads(dest.read_text())
    assert [e["id"] for e in result["events"]] == ["GL-stable"]
    assert len(result["events"][0]["history"]) == 1
    assert result["meta"]["historyRejectedRows"] == 2
    assert result["events"][0]["thermalChange"]["status"] == "insufficient_history"


@pytest.mark.parametrize("body", ["corrupt", '{"events": []}', '{"meta":{"source":"firms_live","scope":"india"},"events":[]}',
                                  '{"meta":{"source":"firms_live"},"events":[],"extra":NaN}'])
def test_corrupt_previous_snapshot_fails_before_replacing_any_output(tmp_path, body):
    dest = tmp_path / "global-events.json"
    dest.write_text(body)
    companion = dest.with_suffix(".json.gz")
    companion.write_bytes(b"prior compressed")
    with pytest.raises(ValueError, match="Previous global snapshot"):
        export_global_payload(snapshot("2026-10-04"), dest)
    assert dest.read_text() == body
    assert companion.read_bytes() == b"prior compressed"
    assert not (tmp_path / "global-facilities.geojson").exists()


def test_snapshot_dedupe_does_not_hide_unobserved_group(tmp_path):
    dest = tmp_path / "global-events.json"
    payload = snapshot("2026-10-01")
    payload["events"][0]["history"].append({**payload["events"][0]["history"][0], "frp": 0, "frpObserved": False})
    export_global_payload(payload, dest)
    for day in ["2026-10-02", "2026-10-03", "2026-10-04"]:
        export_global_payload(snapshot(day, 30 if day == "2026-10-04" else 10), dest)
    result = json.loads(dest.read_text())["events"][0]["thermalChange"]
    assert result["status"] == "insufficient_history" and result["observationDays"] == 2


@pytest.mark.parametrize("current_rows", [[], [{"date": None, "frp": None}],
                                         [{"date": "2026-10-04", "frp": None}]])
def test_cached_same_day_cannot_replace_missing_or_invalid_current_input(tmp_path, current_rows):
    dest = tmp_path / "global-events.json"
    for day in ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]:
        export_global_payload(snapshot(day, 30 if day == "2026-10-04" else 10), dest)
    previous = dest.read_bytes()
    payload = snapshot("2026-10-04", 30, history=current_rows)
    before = copy.deepcopy(payload)
    assert analyze_thermal_change(payload["events"][0])["status"] == "insufficient_history"
    export_global_payload(payload, dest)
    result = json.loads(dest.read_text())["events"][0]
    assert result["thermalChange"]["status"] == "insufficient_history"
    assert result["thermalChange"]["currentFrp"] is None
    assert result["thermalChange"]["priorityPoints"] == 0
    assert not any(r.get("date") == "2026-10-04" and r.get("frp") == 30 for r in result["history"])
    assert payload == before
    assert previous != dest.read_bytes()


def test_cached_same_day_peak_and_sensor_groups_never_override_current_input(tmp_path):
    dest = tmp_path / "global-events.json"
    prior = snapshot("2026-10-04", 300, satellite="N21")
    prior["events"][0]["history"] += [{**observation(day, 10), "frpObserved": True}
                                      for day in ["2026-10-01", "2026-10-02", "2026-10-03"]]
    dest.write_text(json.dumps(prior))
    export_global_payload(snapshot("2026-10-04", 10), dest)
    result = json.loads(dest.read_text())["events"][0]
    assert result["thermalChange"]["status"] == "stable"
    assert result["thermalChange"]["currentFrp"] == 10
    assert [r["satellite"] for r in result["history"] if r["date"] == "2026-10-04"] == ["N20"]


def test_prior_history_cannot_extend_beyond_prior_event_acquisition_day(tmp_path):
    dest = tmp_path / "global-events.json"
    prior = snapshot("2026-10-01")
    prior["events"][0]["history"] += [observation(day, 10) for day in ["2026-10-02", "2026-10-03"]]
    dest.write_text(json.dumps(prior))
    export_global_payload(snapshot("2026-10-04", 30), dest)
    result = json.loads(dest.read_text())
    analysis = result["events"][0]["thermalChange"]
    assert analysis["status"] == "insufficient_history"
    assert analysis["observationDays"] == 1
    assert result["meta"]["historyRejectedRows"] == 2


@pytest.mark.parametrize("generated", ["2026-10-01T23:00:00Z", "2026-10-02T01:00:00+02:00"])
def test_prior_history_is_bounded_by_snapshot_generation_utc_day(tmp_path, generated):
    dest = tmp_path / "global-events.json"
    prior = snapshot("2026-10-03")
    prior["meta"]["generatedAt"] = generated
    prior["events"][0]["history"] += [observation(day, 10) for day in ["2026-10-01", "2026-10-02"]]
    dest.write_text(json.dumps(prior))
    export_global_payload(snapshot("2026-10-04", 30), dest)
    result = json.loads(dest.read_text())
    analysis = result["events"][0]["thermalChange"]
    assert analysis["status"] == "insufficient_history"
    assert analysis["observationDays"] == 1
    assert result["meta"]["historyRejectedRows"] == 2


@pytest.mark.parametrize("acquisition", [None, "invalid"])
def test_undated_prior_event_cannot_contribute_baseline(tmp_path, acquisition):
    dest = tmp_path / "global-events.json"
    prior = snapshot("2026-10-03")
    prior["events"][0]["acqDate"] = acquisition
    prior["events"][0]["history"] += [observation(day, 10) for day in ["2026-10-01", "2026-10-02"]]
    dest.write_text(json.dumps(prior))
    export_global_payload(snapshot("2026-10-04", 30), dest)
    assert json.loads(dest.read_text())["events"][0]["thermalChange"]["observationDays"] == 0


@pytest.mark.parametrize("regional", [False, True])
def test_export_retains_full_days_and_provenance(regional):
    rows = []
    for day, frp in [("2026-10-01", 10), ("2026-10-02", 12), ("2026-10-03", 8), ("2026-10-04", 30)]:
        for minute in range(20):
            rows.append(dict(grid_cell="cell", acq_date=day, frp=frp, confidence_numeric=60,
                             satellite="N20", instrument="VIIRS", daynight="N", acq_time=minute,
                             latitude=20, longitude=80))
    detail = pd.DataFrame(rows)
    summary = pd.DataFrame([dict(grid_cell="cell", event_id="test", max_frp=999,
                                risk_score=1, last_detected="2026-10-04")])
    exported = (transform_regional_to_holo_events if regional else transform_national_to_holo_events)(detail, summary)[0]
    assert len(exported["history"]) == 80  # Not the last 10/14 detections.
    assert exported["history"][0]["satellite"] == "N20"
    assert exported["history"][0]["acq_time"] == 0
    assert exported["thermalChange"]["baselineFrp"] == 10
    assert exported["thermalChange"]["currentFrp"] == 30
    assert exported["thermalChange"]["observationDays"] == 3
    assert exported["thermalChange"]["status"] == "elevated"


def test_export_does_not_fabricate_history_or_zero_frp():
    summary = pd.DataFrame([dict(grid_cell="cell", risk_score=1)])
    exported = transform_national_to_holo_events(None, summary)[0]
    assert exported["history"] == []
    assert exported["thermalChange"]["status"] == "insufficient_history"
    detail = pd.DataFrame([dict(grid_cell="cell", acq_date="2026-10-04", satellite="N20", daynight="N")])
    exported = transform_national_to_holo_events(detail, summary)[0]
    assert exported["history"][0]["frp"] is None
    assert exported["thermalChange"]["currentFrp"] is None


def test_export_bounds_by_calendar_days():
    detail = pd.DataFrame([dict(grid_cell="cell", acq_date=day, frp=10, satellite="N20", daynight="N")
                           for day in ["2026-09-03", "2026-09-04", "2026-10-04"]])
    exported = transform_national_to_holo_events(detail, pd.DataFrame([dict(grid_cell="cell")]))[0]
    assert [r["date"] for r in exported["history"]] == ["2026-09-04", "2026-10-04"]
    assert exported["thermalChange"]["observationDays"] == 1
    assert exported["thermalChange"]["gaps"] == 29


@pytest.mark.parametrize("wrapped", [False, True])
def test_offline_augmentation_preserves_source_and_every_other_field(tmp_path, wrapped):
    e = {**event(), "custom": {"operator": "unchanged"}, "thermalChange": {"status": "stale"}}
    payload = {"meta": {"source": "local_cache"}, "events": [e], "extra": [1, 2]} if wrapped else [e]
    source, destination = tmp_path / "source.json", tmp_path / "copy.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    before = source.read_bytes()
    augment_thermal_snapshot(source, destination)
    assert source.read_bytes() == before
    actual = json.loads(destination.read_text(encoding="utf-8"))
    expected = copy.deepcopy(payload)
    (expected["events"] if wrapped else expected)[0]["thermalChange"] = analyze_thermal_change(e)
    assert actual == expected
    with pytest.raises(ValueError, match="differ"):
        augment_thermal_snapshot(source, source)
    assert source.read_bytes() == before


def test_global_export_precomputes_without_mutating_payload(tmp_path):
    payload = {"meta": {"source": "firms_live"}, "events": [event()]}
    before = copy.deepcopy(payload)
    destination = export_global_payload(payload, tmp_path / "global-events.json")
    assert payload == before
    exported = json.loads(destination.read_text())["events"][0]
    assert exported["thermalChange"] == analyze_thermal_change(event())


def test_augmentation_refreshes_existing_gzip_only(tmp_path):
    source, destination = tmp_path / "source.json", tmp_path / "global-events.json"
    source.write_text(json.dumps({"events": [event()]}))
    companion = destination.with_suffix(".json.gz")
    augment_thermal_snapshot(source, destination)
    assert not companion.exists()
    companion.write_bytes(gzip.compress(b"stale"))
    augment_thermal_snapshot(source, destination)
    assert gzip.decompress(companion.read_bytes()) == destination.read_bytes()
    first = companion.read_bytes()
    augment_thermal_snapshot(source, destination)
    assert companion.read_bytes() == first


def test_invalid_snapshot_preserves_destination_and_gzip(tmp_path):
    source, destination = tmp_path / "source.json", tmp_path / "events.json"
    source.write_text('{"events": [null]}')
    destination.write_bytes(b"previous")
    companion = destination.with_suffix(".json.gz")
    companion.write_bytes(b"previous gzip")
    with pytest.raises(ValueError, match="events array"):
        augment_thermal_snapshot(source, destination)
    assert destination.read_bytes() == b"previous"
    assert companion.read_bytes() == b"previous gzip"


def test_offline_cli_and_legacy_insufficient_history(tmp_path):
    source, destination = tmp_path / "legacy.json", tmp_path / "output.json"
    legacy = event()
    legacy["history"] = [{"date": r["date"], "frp": r["frp"]} for r in legacy["history"]]
    source.write_text(json.dumps({"events": [legacy]}))
    subprocess.run([sys.executable, "-m", "src.utils.export_3d_globe", "--thermal-input", str(source),
                    "--thermal-output", str(destination)], cwd=ROOT, check=True, capture_output=True)
    assert json.loads(destination.read_text())["events"][0]["thermalChange"]["status"] == "insufficient_history"
