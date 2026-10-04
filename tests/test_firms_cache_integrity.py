import os
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

import config
from src.firms.fetch import FirmsAPIError, _cache_path, _fetch_chunk, fetch_hotspots

GOOD = "latitude,longitude,acq_date,acq_time,frp,confidence,satellite\n22.8,86.18,2026-09-01,0130,5,80,N\n"


def test_malformed_response_does_not_replace_usable_stale_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    path = _cache_path(f"area-{config.FIRMS_AREA_STR}", "VIIRS_SNPP_NRT", 1, "2026-09-01")
    path.write_text(GOOD)
    old = time.time() - (config.FIRMS_CACHE_TTL_HOURS + 1) * 3600
    os.utime(path, (old, old))
    response = MagicMock(text="unexpected,column\nwrong,schema\n")
    with patch("requests.get", return_value=response), patch("time.sleep"):
        frame = _fetch_chunk("VIIRS_SNPP_NRT", 1, "2026-09-01", "TEST")
    assert frame.attrs["source"] == "local_cache"
    assert frame.attrs["stale_cache_fallback"] is True
    assert path.read_text() == GOOD
    assert frame.acq_time.iloc[0] == "0130"


def test_corrupt_fresh_cache_is_rejected_when_network_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    path = _cache_path(f"area-{config.FIRMS_AREA_STR}", "VIIRS_SNPP_NRT", 1, "2026-09-01")
    path.write_text("not,a,feed\n")
    with patch("requests.get", side_effect=requests.ConnectionError("offline")), patch("time.sleep"):
        with pytest.raises(FirmsAPIError):
            _fetch_chunk("VIIRS_SNPP_NRT", 1, "2026-09-01", "TEST")


def test_regional_aggregate_preserves_cached_origin(tmp_path, monkeypatch):
    import pandas as pd
    import io

    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    frame = pd.read_csv(io.StringIO(GOOD))
    frame.attrs["source"] = "local_cache"
    with patch("src.firms.fetch._fetch_chunk", return_value=frame):
        result = fetch_hotspots(sources=["VIIRS_SNPP_NRT"], total_days=1, api_key="TEST")
    assert result.attrs["source"] == "local_cache"
