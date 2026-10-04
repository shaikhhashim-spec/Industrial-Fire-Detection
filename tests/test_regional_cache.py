from unittest.mock import patch

import pandas as pd
import pytest

import config
from src.pipeline import load_hotspots

CSV = "latitude,longitude,acq_date,acq_time,frp,confidence,satellite\n22.8,86.18,2026-09-01,0130,5,80,N\n"


def test_offline_fallback_skips_corrupt_empty_and_out_of_region_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    monkeypatch.setattr(config, "FIRMS_API_KEY", "")
    (tmp_path / "firms_2026-09-01.csv").write_text(CSV)
    (tmp_path / "firms_2026-09-02.csv").write_text(CSV.replace("22.8,86.18", "1,1"))
    (tmp_path / "firms_2026-09-03.csv").write_text(CSV.splitlines()[0] + "\n")
    (tmp_path / "firms_2026-09-04.csv").write_text("broken\ncache\n")
    with patch("requests.get", side_effect=AssertionError("Offline test must not use network")):
        frame, source = load_hotspots()
    assert source == "local_cache"
    assert frame.acq_date.iloc[0] == pd.Timestamp("2026-09-01")
    assert frame.acq_time.iloc[0] == "0130"


def test_no_usable_cache_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    monkeypatch.setattr(config, "FIRMS_API_KEY", "")
    with pytest.raises(RuntimeError, match="no previous live pull is cached"):
        load_hotspots()


def test_fetcher_cache_provenance_is_not_reported_as_live(monkeypatch):
    monkeypatch.setattr(config, "FIRMS_API_KEY", "TEST")
    frame = pd.DataFrame({"latitude": [22.8]})
    frame.attrs["source"] = "local_cache"
    with patch("src.pipeline.firms_fetch.fetch_hotspots", return_value=frame):
        assert load_hotspots()[1] == "local_cache"
