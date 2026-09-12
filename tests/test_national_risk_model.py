import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from src.national import risk_model


def _event(**over):
    base = {
        "grid_cell": "21.0_85.0",
        "state": "Odisha",
        "category": "Likely Industrial Fire",
        "risk_score": 80.0,
        "risk_level": "CRITICAL",
        "risk_pts_persistence": 20.0,
        "risk_pts_frp": 35.0,
        "risk_pts_confidence": 25.0,
        "max_frp": 40.0,
        "avg_frp": 20.0,
        "persistence_days": 6,
        "observation_count": 12,
        "avg_confidence": 85.0,
        "corroborated": True,
        "facility": {"name": "Rourkela Steel Plant", "kind": "steel / iron works", "distanceKm": 0.8},
        "evidence": {"days": 6, "detections": 12, "maxFrp": 40.0, "nightPasses": 5,
                     "lowConfidenceShare": 0.0},
    }
    base.update(over)
    return base


class TestRiskFactors(unittest.TestCase):
    def test_factors_are_ranked_and_sum_to_the_score(self):
        row = _event()
        factors = risk_model.risk_factors(row, window_days=30)
        self.assertEqual([f["label"] for f in factors],
                         ["Heat output", "Detection confidence", "Persistence"])
        self.assertAlmostEqual(sum(f["points"] for f in factors), 80.0, places=1)
        self.assertAlmostEqual(sum(f["share"] for f in factors), 1.0, places=2)

    def test_factor_values_read_in_analyst_units(self):
        factors = risk_model.risk_factors(_event(), window_days=30)
        by_label = {f["label"]: f for f in factors}
        self.assertEqual(by_label["Persistence"]["value"], "6 of 30 days")
        self.assertEqual(by_label["Heat output"]["value"], "40.0 MW peak")
        self.assertIn("8 MW", by_label["Heat output"]["detail"])

    def test_missing_components_do_not_raise(self):
        row = _event(risk_pts_persistence=np.nan, risk_pts_frp=None, risk_pts_confidence=np.nan)
        self.assertEqual(risk_model.risk_factors(row, 30), [])
        self.assertIn("80", risk_model.risk_summary(row, []))

    def test_summary_names_the_tier_and_the_lead_factor(self):
        row = _event()
        summary = risk_model.risk_summary(row, risk_model.risk_factors(row, 30))
        self.assertIn("critical risk", summary)
        self.assertIn("heat output", summary)


class TestActions(unittest.TestCase):
    def test_industrial_fire_escalates_and_names_the_facility(self):
        actions = risk_model.recommend_actions(_event())
        self.assertEqual(actions[0]["urgency"], "Now")
        self.assertTrue(any("Rourkela Steel Plant" in a["step"] + a["detail"] for a in actions))

    def test_persistent_industrial_activity_does_not_dispatch_a_response(self):
        actions = risk_model.recommend_actions(
            _event(category="Persistent Industrial Activity", risk_level="HIGH", risk_score=70.0)
        )
        self.assertNotIn("Now", [a["urgency"] for a in actions])
        self.assertIn("operating pattern", " ".join(a["step"] for a in actions))

    def test_agricultural_burning_is_routed_away_from_fire_response(self):
        actions = risk_model.recommend_actions(
            _event(category="Likely Agricultural Burning", facility=None, risk_level="MODERATE")
        )
        joined = " ".join(a["step"] + a["detail"] for a in actions)
        self.assertIn("crop-residue", joined)
        self.assertIn("Do not dispatch", joined)

    def test_uncorroborated_events_are_flagged_before_anything_else(self):
        actions = risk_model.recommend_actions(
            _event(category="Requires Verification", corroborated=False, risk_level="LOW", facility=None)
        )
        self.assertEqual(actions[0]["step"], "Treat as unconfirmed")

    def test_a_critical_glint_is_never_escalated(self):
        actions = risk_model.recommend_actions(
            _event(category="Sun Glint / False Positive", risk_level="CRITICAL", facility=None)
        )
        self.assertNotIn("Now", [a["urgency"] for a in actions])


class TestModelCheck(unittest.TestCase):
    def _frame(self, n=200):
        rng = np.random.default_rng(0)
        rows = []
        for i in range(n):
            industrial = i % 2 == 0
            rows.append(_event(
                grid_cell=f"cell{i}",
                category="Persistent Industrial Activity" if industrial else "Requires Verification",
                max_frp=float(rng.uniform(20, 60) if industrial else rng.uniform(0.5, 4)),
                avg_frp=float(rng.uniform(10, 30) if industrial else rng.uniform(0.5, 3)),
                persistence_days=int(rng.integers(8, 25) if industrial else 1),
                observation_count=int(rng.integers(20, 100) if industrial else 1),
                facility=None if not industrial else {"name": "Works", "kind": "steel / iron works",
                                                      "distanceKm": 0.5},
                evidence={"days": int(rng.integers(8, 25)) if industrial else 1,
                          "detections": int(rng.integers(20, 100)) if industrial else 1,
                          "maxFrp": 30.0 if industrial else 1.0,
                          "nightPasses": 10 if industrial else 0,
                          "lowConfidenceShare": 0.0 if industrial else 0.8},
            ))
        return pd.DataFrame(rows)

    def test_separable_categories_are_reproduced(self):
        labels, confidence, info = risk_model.validate_categories(self._frame())
        self.assertTrue(info["trained"])
        self.assertGreater(info["holdout_agreement"], 0.9)
        self.assertEqual(len(labels), 200)
        self.assertTrue((confidence >= 0).all() and (confidence <= 1).all())
        self.assertIn("feature_importances", info)

    def test_too_little_data_reports_instead_of_faking_a_model(self):
        labels, confidence, info = risk_model.validate_categories(self._frame(10))
        self.assertFalse(info["trained"])
        self.assertTrue(labels.empty)
        self.assertIn("minimum", info["reason"])
        self.assertIn("caveat", info)

    def test_enrich_adds_every_field_and_ranks_by_score(self):
        ev = self._frame(120)
        ev.loc[0, "risk_score"] = 99.0
        out, info = risk_model.enrich_risk(ev, window_days=config.NATIONAL_HISTORY_DAYS)
        for col in ("risk_factors", "risk_summary", "actions", "model_check", "priority"):
            self.assertIn(col, out.columns)
        self.assertEqual(int(out.loc[0, "priority"]), 1)
        self.assertEqual(sorted(out["priority"]), list(range(1, len(out) + 1)))
        self.assertTrue(info["trained"])
        self.assertIn("agrees", out.loc[0, "model_check"])

    def test_enrich_on_an_empty_frame_is_safe(self):
        out, info = risk_model.enrich_risk(pd.DataFrame(), window_days=30)
        self.assertTrue(out.empty)
        self.assertFalse(info["trained"])


if __name__ == "__main__":
    unittest.main()
