from unittest.mock import MagicMock, patch

import pytest
import requests

import config
from src.firms import fetch as firms_fetch

GOOD_CSV = "latitude,longitude,acq_date,acq_time,frp,confidence,satellite\n22.8,86.18,2026-08-01,130,5.0,80,N\n"


def _resp(text, status=200):
    r = MagicMock()
    r.text = text
    r.status_code = status
    r.raise_for_status.return_value = None
    return r


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)


def test_missing_key_raises_auth_error_without_network_call(monkeypatch):
    monkeypatch.setattr(config, "FIRMS_API_KEY", "")  # isolate from a real key configured in .env
    with patch("requests.get") as mock_get:
        with pytest.raises(firms_fetch.FirmsAuthError):
            firms_fetch.fetch_hotspots(api_key="")
    mock_get.assert_not_called()


def test_invalid_key_response_raises_auth_error_not_retried():
    with patch("requests.get", return_value=_resp("Invalid MAP_KEY")) as mock_get:
        with pytest.raises(firms_fetch.FirmsAuthError):
            firms_fetch._fetch_chunk("VIIRS_SNPP_NRT", 5, "2026-08-28", "BADKEY")
    assert mock_get.call_count == 1


def test_successful_fetch_returns_dataframe_and_caches(tmp_path):
    with patch("requests.get", return_value=_resp(GOOD_CSV)) as mock_get:
        df = firms_fetch._fetch_chunk("VIIRS_SNPP_NRT", 5, "2026-08-28", "TESTKEY")
    assert len(df) == 1
    assert "latitude" in df.columns
    mock_get.assert_called_once()
    assert list(tmp_path.glob("*.csv"))


def test_transient_failure_then_success_retries():
    side_effects = [requests.exceptions.ConnectionError("boom"), _resp(GOOD_CSV)]
    with patch("requests.get", side_effect=side_effects) as mock_get, patch("time.sleep", return_value=None):
        df = firms_fetch._fetch_chunk("VIIRS_SNPP_NRT", 5, "2026-08-28", "TESTKEY")
    assert len(df) == 1
    assert mock_get.call_count == 2


def test_all_retries_fail_no_cache_raises():
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("down")), \
         patch("time.sleep", return_value=None):
        with pytest.raises(firms_fetch.FirmsAPIError):
            firms_fetch._fetch_chunk("VIIRS_SNPP_NRT", 5, "2026-08-28", "TESTKEY")


def test_empty_response_produces_empty_dataframe_not_crash():
    empty_csv = "latitude,longitude,acq_date,acq_time,frp,confidence,satellite\n"
    with patch("requests.get", return_value=_resp(empty_csv)):
        df = firms_fetch._fetch_chunk("VIIRS_SNPP_NRT", 5, "2026-08-28", "TESTKEY")
    assert df.empty


def test_check_map_key_invalid():
    with patch("requests.get", return_value=_resp("Invalid MAP_KEY provided")):
        with pytest.raises(firms_fetch.FirmsAuthError):
            firms_fetch.check_map_key("BADKEY")


def test_check_map_key_valid():
    with patch("requests.get", return_value=_resp('{"transaction_limit": 5000}')):
        info = firms_fetch.check_map_key("GOODKEY")
    assert "transaction_limit" in info["raw"]
