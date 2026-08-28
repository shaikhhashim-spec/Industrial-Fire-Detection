"""
Tests for fetch_firms_data — all network calls are mocked, so these run
without hitting the real FIRMS API or needing a MAP_KEY.

Run with:  python -m unittest test_fetch_firms_data -v
(or: python -m pytest test_fetch_firms_data.py -v, if pytest is installed)
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests

from fetch_firms_data import (
    fetch_firms_data,
    fetch_multi_source,
    add_persistence_flags,
    FirmsAPIError,
    FirmsAuthError,
)
import pandas as pd

GOOD_CSV = (
    "latitude,longitude,brightness,acq_date,acq_time,confidence,frp\n"
    "34.05,-118.24,320.1,2026-08-25,0930,85,12.4\n"
    "36.77,-119.42,305.7,2026-08-25,0930,60,7.1\n"
)


def _mock_response(text, status=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status.return_value = None
    return resp


class FetchFirmsDataTests(unittest.TestCase):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_successful_fetch_returns_dataframe_and_caches(self):
        with patch("requests.get", return_value=_mock_response(GOOD_CSV)) as mock_get:
            df = fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir,
            )
        self.assertEqual(len(df), 2)
        self.assertIn("latitude", df.columns)
        mock_get.assert_called_once()
        cached_files = list(Path(self.cache_dir).glob("*.csv"))
        self.assertEqual(len(cached_files), 1)

    def test_missing_map_key_raises_auth_error_immediately(self):
        with patch("requests.get") as mock_get:
            with self.assertRaises(FirmsAuthError):
                fetch_firms_data(
                    source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                    map_key=None, cache_dir=self.cache_dir,
                )
        mock_get.assert_not_called()  # never even tries the network

    def test_invalid_key_response_not_retried(self):
        bad_resp = _mock_response("Invalid MAP_KEY")
        with patch("requests.get", return_value=bad_resp) as mock_get:
            with self.assertRaises(FirmsAuthError):
                fetch_firms_data(
                    source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                    map_key="BADKEY", cache_dir=self.cache_dir, max_retries=4,
                )
        self.assertEqual(mock_get.call_count, 1)  # auth errors don't burn retries

    def test_transient_failure_then_success_retries_and_succeeds(self):
        side_effects = [
            requests.exceptions.ConnectionError("boom"),
            requests.exceptions.Timeout("slow"),
            _mock_response(GOOD_CSV),
        ]
        with patch("requests.get", side_effect=side_effects) as mock_get, \
             patch("time.sleep", return_value=None):  # skip real backoff delay in tests
            df = fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, max_retries=4,
            )
        self.assertEqual(len(df), 2)
        self.assertEqual(mock_get.call_count, 3)

    def test_all_retries_fail_falls_back_to_stale_cache(self):
        # Prime the cache with a prior successful fetch.
        with patch("requests.get", return_value=_mock_response(GOOD_CSV)):
            fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, cache_ttl_hours=0,
            )
        # Now every network attempt fails.
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("down")), \
             patch("time.sleep", return_value=None):
            df = fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, cache_ttl_hours=0, max_retries=3,
            )
        self.assertEqual(len(df), 2)
        self.assertTrue(df.attrs.get("stale_cache_fallback"))

    def test_all_retries_fail_no_cache_raises(self):
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("down")), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(FirmsAPIError):
                fetch_firms_data(
                    source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                    map_key="TESTKEY", cache_dir=self.cache_dir, max_retries=3,
                )

    def test_fresh_cache_served_without_network_call(self):
        with patch("requests.get", return_value=_mock_response(GOOD_CSV)):
            fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, cache_ttl_hours=6,
            )
        with patch("requests.get") as mock_get:
            df = fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, cache_ttl_hours=6,
            )
        mock_get.assert_not_called()
        self.assertEqual(len(df), 2)

    def test_detection_id_present_and_stable_across_refetch(self):
        with patch("requests.get", return_value=_mock_response(GOOD_CSV)):
            df1 = fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, use_cache=False,
            )
        with patch("requests.get", return_value=_mock_response(GOOD_CSV)):
            df2 = fetch_firms_data(
                source="VIIRS_SNPP_NRT", day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir, use_cache=False,
            )
        self.assertIn("detection_id", df1.columns)
        self.assertEqual(list(df1["detection_id"]), list(df2["detection_id"]))
        # Same underlying row -> same id; different rows -> different ids.
        self.assertEqual(len(set(df1["detection_id"])), len(df1))

    def test_multi_source_fetch_concatenates_and_tags_source(self):
        with patch("requests.get", return_value=_mock_response(GOOD_CSV)) as mock_get:
            df = fetch_multi_source(
                sources=["VIIRS_SNPP_NRT", "MODIS_NRT"],
                day_range=1, area_coords="-125,32,-114,42",
                map_key="TESTKEY", cache_dir=self.cache_dir,
            )
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(df), 4)  # 2 rows x 2 sources
        self.assertEqual(set(df["query_source"]), {"VIIRS_SNPP_NRT", "MODIS_NRT"})

    def test_persistence_flags_marks_recurring_location(self):
        # Same spot detected on 4 distinct days -> persistent.
        # A different spot detected once -> not persistent.
        rows = []
        for d in ["2026-08-20", "2026-08-21", "2026-08-22", "2026-08-23"]:
            rows.append({"latitude": 23.0000, "longitude": 72.0000, "acq_date": d})
        rows.append({"latitude": 10.0000, "longitude": 40.0000, "acq_date": "2026-08-20"})
        df = pd.DataFrame(rows)

        flagged = add_persistence_flags(df, cluster_radius_km=1.0, min_distinct_days=3)

        persistent_rows = flagged[flagged["latitude"] == 23.0000]
        one_off_rows = flagged[flagged["latitude"] == 10.0000]

        self.assertTrue((persistent_rows["is_persistent_source"]).all())
        self.assertTrue((persistent_rows["cluster_distinct_days"] == 4).all())
        self.assertFalse((one_off_rows["is_persistent_source"]).any())

    def test_persistence_flags_handles_empty_dataframe(self):
        empty = pd.DataFrame(columns=["latitude", "longitude", "acq_date"])
        flagged = add_persistence_flags(empty)
        self.assertIn("is_persistent_source", flagged.columns)
        self.assertEqual(len(flagged), 0)


if __name__ == "__main__":
    unittest.main()
