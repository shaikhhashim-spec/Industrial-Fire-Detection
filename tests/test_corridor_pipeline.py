import config
from src.corridor.pipeline import run_corridor_pipeline


def test_singrauli_registered_in_regions():
    assert "singrauli" in config.REGIONS
    cfg = config.REGIONS["singrauli"]
    assert cfg["name"] == config.SINGRAULI_REGION_NAME
    assert cfg["bbox"] == config.SINGRAULI_BBOX
    assert cfg["detailed"] is False


def test_demo_pipeline_runs_end_to_end():
    info = run_corridor_pipeline("singrauli", demo_mode=True)
    assert info["hotspot_source"] == "demo_data"
    assert info["n_observations"] > 0
    assert info["n_events"] > 0
    assert not info["detail_df"].empty
    assert not info["events_df"].empty


def test_demo_pipeline_events_within_corridor_bbox():
    info = run_corridor_pipeline("singrauli", demo_mode=True)
    bbox = config.SINGRAULI_BBOX
    events = info["events_df"]
    assert (events["latitude"].between(bbox["min_lat"], bbox["max_lat"])).all()
    assert (events["longitude"].between(bbox["min_lon"], bbox["max_lon"])).all()


def test_demo_pipeline_events_have_stable_event_ids():
    info = run_corridor_pipeline("singrauli", demo_mode=True)
    events = info["events_df"]
    assert events["event_id"].str.startswith("TH-").all()
    assert events["event_id"].is_unique


def test_demo_pipeline_risk_levels_are_valid():
    valid_levels = {label for _, _, label in config.RISK_LEVELS}
    info = run_corridor_pipeline("singrauli", demo_mode=True)
    assert set(info["events_df"]["risk_level"].unique()) <= valid_levels
