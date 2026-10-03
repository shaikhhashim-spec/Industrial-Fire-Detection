import datetime as dt
import json

from scripts.pages_refresh_policy import fresh_snapshot, refresh_policy

NOW = dt.datetime(2026, 10, 3, 7, tzinfo=dt.timezone.utc)


def snapshot(path, age=1, source="firms_live", feed_age=None):
    meta = {"source": source, "generatedAt": (NOW - dt.timedelta(hours=age)).isoformat()}
    if feed_age is not None:
        meta["feeds"] = [{"retrievedAt": (NOW - dt.timedelta(hours=feed_age)).isoformat()}]
    path.write_text(json.dumps({"meta": meta, "events": []}))


def test_code_push_reuses_recent_real_snapshots(tmp_path):
    for name in ("events.json", "global-events.json"):
        snapshot(tmp_path / name)
    assert refresh_policy("push", tmp_path, NOW) == {"global": False, "national": False}
    assert refresh_policy("schedule", tmp_path, NOW) == {"global": True, "national": True}
    assert refresh_policy("workflow_dispatch", tmp_path, NOW) == {"global": True, "national": True}


def test_stale_future_or_non_firms_snapshot_is_refreshed(tmp_path):
    path = tmp_path / "events.json"
    for options in ({"age": 7}, {"age": -1}, {"source": "none"}, {"feed_age": 8}):
        snapshot(path, **options)
        assert not fresh_snapshot(path, NOW)


def test_missing_or_invalid_snapshot_does_not_block_refresh(tmp_path):
    path = tmp_path / "events.json"
    assert not fresh_snapshot(path, NOW)
    path.write_text("not-json")
    assert not fresh_snapshot(path, NOW)
    path.write_text('{"meta": {"source":"firms_live", "generatedAt":"2026-10-03"}, "events": []}')
    assert not fresh_snapshot(path, NOW)
