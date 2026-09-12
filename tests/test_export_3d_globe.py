"""Unit tests for 3D Holo-View export converter."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import geopandas as gpd
import pandas as pd
import json

from src.utils.export_3d_globe import (
    _normalize_satellite,
    export_pipeline_events_for_holo_view,
    transform_regional_to_holo_events,
    transform_national_to_holo_events,
)


class TestNormalizeSatellite(unittest.TestCase):
    """evidence.satellites carries the humanized short names
    national/context.py's `_sat_name` produces ("Aqua", "N20", ...), not raw
    FIRMS source tags — both forms have to resolve to the same label, or a
    real regression silently relabels every MODIS detection as VIIRS S-NPP."""

    def test_humanized_modis_names_are_recognized(self):
        self.assertEqual(_normalize_satellite("Aqua"), "MODIS Aqua")
        self.assertEqual(_normalize_satellite("Terra"), "MODIS Terra")

    def test_raw_firms_source_tags_are_recognized(self):
        self.assertEqual(_normalize_satellite("MODIS_NRT"), "MODIS Terra")
        self.assertEqual(_normalize_satellite("VIIRS_NOAA20_NRT"), "VIIRS NOAA-20")
        self.assertEqual(_normalize_satellite("VIIRS_NOAA21_NRT"), "VIIRS NOAA-21")

    def test_viirs_short_codes(self):
        self.assertEqual(_normalize_satellite("N20"), "VIIRS NOAA-20")
        self.assertEqual(_normalize_satellite("N21"), "VIIRS NOAA-21")
        self.assertEqual(_normalize_satellite("N"), "VIIRS S-NPP")

    def test_empty_or_missing_defaults_to_snpp(self):
        self.assertEqual(_normalize_satellite(""), "VIIRS S-NPP")
        self.assertEqual(_normalize_satellite(None), "VIIRS S-NPP")
        self.assertEqual(_normalize_satellite(float("nan")), "VIIRS S-NPP")


class TestExport3DGlobe(unittest.TestCase):
    def test_transform_regional_to_holo_events(self):
        cluster_df = pd.DataFrame([
            {
                "event_id": "TI-TEST01",
                "grid_cell": "CELL_01",
                "latitude": 22.8,
                "longitude": 86.2,
                "dominant_label": "Likely Industrial Fire",
                "risk_score": 85.0,
                "risk_level": "CRITICAL",
                "max_frp": 25.4,
                "avg_frp": 18.2,
                "persistence_30d": 12,
                "detection_count": 16,
                "zone_type": "industrial",
                "zone_kind": "steel_mill",
                "status": "CRITICAL",
                "last_detected": "2026-08-30",
                "satellites": ["VIIRS_SNPP_NRT"],
                "avg_confidence": 90.0,
            }
        ])
        detail_gdf = gpd.GeoDataFrame([
            {
                "grid_cell": "CELL_01",
                "acq_date": pd.Timestamp("2026-08-30"),
                "frp": 25.4,
                "confidence_numeric": 90.0,
                "brightness": 340.0,
                "daynight": "D",
            }
        ])

        events = transform_regional_to_holo_events(detail_gdf, cluster_df)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["id"], "TI-TEST01")
        self.assertEqual(e["category"], "Likely Industrial Fire")
        self.assertEqual(e["riskScore"], 85)
        self.assertEqual(e["riskLevel"], "CRITICAL")
        self.assertEqual(e["frp"], 25.4)
        self.assertEqual(e["persistenceDays"], 12)
        self.assertEqual(e["detectionCount"], 16)
        self.assertEqual(e["satellite"], "VIIRS S-NPP")
        self.assertEqual(len(e["history"]), 1)

    def test_transform_national_to_holo_events(self):
        events_df = pd.DataFrame([
            {
                "event_id": "NAT-TEST01",
                "grid_cell": "NAT_CELL_01",
                "state": "Odisha",
                "latitude": 21.5,
                "longitude": 84.8,
                "avg_frp": 14.5,
                "persistence_days": 6,
                "is_persistent": True,
                "risk_score": 62.0,
                "risk_level": "HIGH",
                "observation_count": 8,
                "satellite": "VIIRS_NOAA20_NRT",
                "avg_confidence": 85.0,
            }
        ])

        events = transform_national_to_holo_events(None, events_df)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["id"], "NAT-TEST01")
        self.assertIn("Odisha", e["region"])
        self.assertEqual(e["riskScore"], 62)
        self.assertEqual(e["riskLevel"], "HIGH")
        self.assertEqual(e["persistenceDays"], 6)

    def test_export_writes_meta_and_events(self):
        with TemporaryDirectory() as td:
            dest = Path(td) / "events.json"
            events = export_pipeline_events_for_holo_view(destinations=[dest])
            self.assertGreater(len(events), 0)
            payload = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["events"]), len(events))
            # meta.source says honestly where the globe's points came from
            self.assertIn(payload["meta"]["source"], {"firms_live", "mixed", "none"})


if __name__ == "__main__":
    unittest.main()

