import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from src.cameras import coverage, registry

ROURKELA = (22.2604, 84.8536)


def _camera(**over):
    base = {
        "name": "Rourkela Steel Plant, south gate",
        "operator": "SAIL Rourkela",
        "kind": "Plant control room",
        "latitude": ROURKELA[0],
        "longitude": ROURKELA[1],
        "stream_url": "https://example.org/live/stream.m3u8",
        "coverage_km": 3.0,
    }
    base.update(over)
    return base


def _events(rows):
    return pd.DataFrame([
        {"event_id": f"TH-{i:03d}", "latitude": lat, "longitude": lon,
         "risk_score": score, "risk_level": level, "state": "Odisha"}
        for i, (lat, lon, score, level) in enumerate(rows)
    ])


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(config, "CAMERA_REGISTRY_PATH", Path(self._tmp.name) / "cameras.json")
        patcher.start()
        self.addCleanup(patcher.stop)


class TestStreamTypes(unittest.TestCase):
    def test_type_is_inferred_from_the_url(self):
        self.assertEqual(registry.infer_stream_type("https://x.org/a/b.m3u8"), "hls")
        self.assertEqual(registry.infer_stream_type("https://x.org/a/b.m3u8?token=1"), "hls")
        self.assertEqual(registry.infer_stream_type("https://www.youtube.com/watch?v=abc"), "youtube")
        self.assertEqual(registry.infer_stream_type("https://youtu.be/abc"), "youtube")
        self.assertEqual(registry.infer_stream_type("https://cam/axis-cgi/mjpg/video.cgi"), "mjpeg")
        self.assertEqual(registry.infer_stream_type("https://cam/snapshot.jpg"), "image")
        self.assertEqual(registry.infer_stream_type("https://portal.example/viewer"), "iframe")

    def test_youtube_links_become_embeds(self):
        self.assertEqual(registry.youtube_embed("https://youtu.be/abc123"),
                         "https://www.youtube.com/embed/abc123?autoplay=1&mute=1")
        self.assertEqual(registry.youtube_embed("https://www.youtube.com/watch?v=abc123&t=4"),
                         "https://www.youtube.com/embed/abc123?autoplay=1&mute=1")
        self.assertEqual(registry.youtube_embed("https://www.youtube.com/live/abc123"),
                         "https://www.youtube.com/embed/abc123?autoplay=1&mute=1")
        self.assertIsNone(registry.youtube_embed("https://vimeo.com/1"))


class TestIndiaOnly(unittest.TestCase):
    def test_indian_coordinates_are_accepted(self):
        self.assertTrue(registry.inside_india(*ROURKELA))

    def test_neighbouring_countries_and_open_sea_are_rejected(self):
        self.assertFalse(registry.inside_india(24.86, 67.01))   # Karachi
        self.assertFalse(registry.inside_india(27.71, 85.32))   # Kathmandu
        self.assertFalse(registry.inside_india(15.0, 88.0))     # Bay of Bengal
        self.assertFalse(registry.inside_india(48.85, 2.35))    # far outside the bbox

    def test_validation_explains_why_a_point_is_rejected(self):
        problems = registry.validate(_camera(latitude=24.86, longitude=67.01))
        self.assertTrue(any("outside India" in p for p in problems))


class TestValidation(unittest.TestCase):
    def test_a_good_camera_has_no_problems(self):
        self.assertEqual(registry.validate(_camera()), [])

    def test_missing_name_and_url_are_reported(self):
        problems = registry.validate(_camera(name="  ", stream_url=""))
        self.assertEqual(len(problems), 2)

    def test_plain_http_is_flagged_as_unloadable(self):
        problems = registry.validate(_camera(stream_url="http://cam.example/stream.m3u8"))
        self.assertTrue(any("https" in p for p in problems))

    def test_a_non_url_is_rejected(self):
        self.assertTrue(any("http" in p for p in registry.validate(_camera(stream_url="rtsp://cam/1"))))

    def test_coverage_radius_has_to_be_sane(self):
        self.assertTrue(registry.validate(_camera(coverage_km=0)))
        self.assertTrue(registry.validate(_camera(coverage_km=500)))


class TestStorage(RegistryTestCase):
    def test_add_load_and_remove(self):
        record, problems = registry.add(_camera())
        self.assertEqual(problems, [])
        self.assertTrue(record["id"].startswith("CAM-"))
        self.assertEqual(record["stream_type"], "hls")
        self.assertEqual(len(registry.load()), 1)
        self.assertTrue(registry.remove(record["id"]))
        self.assertEqual(registry.load(), [])
        self.assertFalse(registry.remove(record["id"]))

    def test_an_invalid_camera_is_not_written(self):
        record, problems = registry.add(_camera(latitude=24.86, longitude=67.01))
        self.assertIsNone(record)
        self.assertTrue(problems)
        self.assertEqual(registry.load(), [])

    def test_disabling_removes_it_from_the_active_set(self):
        record, _ = registry.add(_camera())
        registry.set_active(record["id"], False)
        self.assertEqual(registry.active_cameras(), [])
        registry.set_active(record["id"], True)
        self.assertEqual(len(registry.active_cameras()), 1)

    def test_a_corrupt_file_reads_as_empty_rather_than_raising(self):
        config.CAMERA_REGISTRY_PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(registry.load(), [])


class TestCoverage(unittest.TestCase):
    def test_events_inside_the_radius_are_covered(self):
        events = _events([
            (22.2604, 84.8536, 80, "CRITICAL"),   # on the camera
            (22.2700, 84.8600, 70, "HIGH"),       # ~1 km away
            (23.5000, 85.5000, 65, "HIGH"),       # far
        ])
        cams = [dict(_camera(), id="CAM-1")]
        report = coverage.summary(events, cams)
        self.assertEqual(report["n_flagged"], 3)
        self.assertEqual(report["n_covered"], 2)
        self.assertEqual(report["n_uncovered"], 1)
        self.assertEqual(len(report["by_camera"]["CAM-1"]), 2)

    def test_only_dispatchable_tiers_count(self):
        events = _events([(22.26, 84.85, 20, "LOW"), (22.27, 84.86, 40, "MODERATE")])
        self.assertEqual(coverage.summary(events, [])["n_flagged"], 0)

    def test_with_no_cameras_everything_is_a_gap(self):
        events = _events([(22.26, 84.85, 80, "CRITICAL")])
        report = coverage.summary(events, [])
        self.assertEqual(report["n_covered"], 0)
        self.assertEqual(report["n_uncovered"], 1)
        self.assertEqual(report["coverage_share"], 0.0)

    def test_siting_picks_the_densest_cluster_first(self):
        rows = [(22.26 + i * 0.005, 84.85, 60 + i, "HIGH") for i in range(5)]  # tight cluster
        rows += [(25.00, 80.00, 90, "CRITICAL")]                               # a lone site
        candidates = coverage.siting_candidates(_events(rows), radius_km=3.0, limit=5)
        self.assertEqual(candidates[0]["events_covered"], 5)
        self.assertEqual(candidates[1]["events_covered"], 1)

    def test_siting_never_double_counts_an_event(self):
        rows = [(22.26 + i * 0.004, 84.85, 60, "HIGH") for i in range(9)]
        candidates = coverage.siting_candidates(_events(rows), radius_km=1.0, limit=9)
        self.assertEqual(sum(c["events_covered"] for c in candidates), 9)

    def test_siting_on_nothing_returns_nothing(self):
        self.assertEqual(coverage.siting_candidates(pd.DataFrame(), radius_km=3.0), [])

    def test_nearest_camera_reports_the_distance(self):
        cams = [dict(_camera(), id="CAM-1")]
        camera, km = coverage.nearest_camera(22.30, 84.90, cams)
        self.assertEqual(camera["id"], "CAM-1")
        self.assertLess(km, 10)
        self.assertEqual(coverage.nearest_camera(22.0, 84.0, [])[0], None)

    def test_covers_matches_the_stated_radius(self):
        camera = dict(_camera(), coverage_km=2.0)
        self.assertTrue(coverage.covers(camera, 22.2650, 84.8536))
        self.assertFalse(coverage.covers(camera, 22.3200, 84.8536))


if __name__ == "__main__":
    unittest.main()
