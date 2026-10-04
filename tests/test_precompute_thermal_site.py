import gzip
import json

import pytest

from scripts.precompute_thermal_site import precompute


def test_assembled_copies_are_enriched_without_mutating_source(tmp_path):
    globe, site = tmp_path / "built", tmp_path / "assembled"
    (globe / "data").mkdir(parents=True)
    source = globe / "data" / "events.json"
    original = json.dumps({"meta": {"source": "firms_live"}, "events": [{"id": "a", "history": []}]})
    source.write_text(original, encoding="utf-8")
    for directory in (site / "globe" / "data", site / "data"):
        directory.mkdir(parents=True)
        (directory / "events.json.gz").write_bytes(gzip.compress(b"old"))
    assert precompute(globe, site) == 1
    assert source.read_text(encoding="utf-8") == original
    for directory in (site / "globe" / "data", site / "data"):
        payload = json.loads((directory / "events.json").read_text(encoding="utf-8"))
        assert payload["events"][0]["thermalChange"]["status"] == "insufficient_history"
        assert gzip.decompress((directory / "events.json.gz").read_bytes()) == (directory / "events.json").read_bytes()


def test_precompute_rejects_using_source_as_destination(tmp_path):
    (tmp_path / "data").mkdir()
    source = tmp_path / "data" / "events.json"
    source.write_text('{"events":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="differ"):
        precompute(tmp_path, tmp_path)
