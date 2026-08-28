import pandas as pd

import config
from src.ml.rules import classify, normalize_confidence


def _row(**overrides):
    base = dict(is_persistent=False, zone_type="other", confidence="n", frp=1.0,
                persistence_days=1, acq_date=pd.Timestamp("2026-08-15"))
    base.update(overrides)
    return base


def test_normalize_confidence_viirs_letters():
    df = pd.DataFrame({"confidence": ["l", "n", "h"]})
    out = normalize_confidence(df)
    assert list(out["confidence_numeric"]) == [30, 60, 90]


def test_normalize_confidence_numeric_passthrough():
    df = pd.DataFrame({"confidence": [15, 72]})
    out = normalize_confidence(df)
    assert list(out["confidence_numeric"]) == [15.0, 72.0]


def test_industrial_persistent_high_conf_high_frp_is_fire():
    df = pd.DataFrame([_row(is_persistent=True, zone_type="industrial", confidence="h",
                             frp=config.FRP_INDUSTRIAL_MIN + 1, persistence_days=10)])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Industrial Fire"
    assert out.loc[0, "rule_evidence"]  # non-empty explanation


def test_industrial_persistent_low_frp_is_low_intensity():
    df = pd.DataFrame([_row(is_persistent=True, zone_type="industrial", confidence="n",
                             frp=0.1, persistence_days=10)])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Persistent Industrial Activity"


def test_industrial_transient_is_flare():
    df = pd.DataFrame([_row(is_persistent=False, zone_type="industrial", confidence="n", persistence_days=1)])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Transient Industrial Flare"


def test_low_confidence_offseason_is_false_positive():
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence="l",
                             acq_date=pd.Timestamp("2026-07-01"))])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Sun Glint / False Positive"


def test_burn_season_non_industrial_is_agricultural():
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence="n",
                             acq_date=pd.Timestamp("2026-11-15"))])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Agricultural Burning"


def test_moderate_conf_offseason_nonindustrial_is_wildfire():
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence="h",
                             acq_date=pd.Timestamp("2026-07-01"))])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Wildfire"


def test_in_agricultural_zone_is_agricultural_even_offseason():
    # Real OSM-polygon evidence should classify as agricultural burning even
    # outside the approximated burn-season months, unlike the month-only path.
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence="n",
                             acq_date=pd.Timestamp("2026-07-01"), in_agricultural_zone=True)])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Agricultural Burning"
    assert "agricultural" in out.loc[0, "rule_evidence"].lower()


def test_near_forest_offseason_wildfire_cites_forest_evidence():
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence="h",
                             acq_date=pd.Timestamp("2026-07-01"), forest_distance_km=0.3)])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Wildfire"
    assert "forest" in out.loc[0, "rule_evidence"].lower()


def test_near_water_moderate_conf_is_false_positive():
    # confidence 55 is between CONF_FLARE_MIN(50) and CONF_INDUSTRIAL_FIRE_MIN(60)
    # — without water-glint evidence this would fall to "Likely Wildfire"
    # (the old conf<50 threshold alone would not catch it); near-water
    # evidence should push it to false-positive instead.
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence=55,
                             acq_date=pd.Timestamp("2026-07-01"), water_distance_km=0.1)])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Sun Glint / False Positive"
    assert "water" in out.loc[0, "rule_evidence"].lower()


def test_same_moderate_conf_without_water_is_wildfire():
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence=55,
                             acq_date=pd.Timestamp("2026-07-01"))])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Wildfire"


def test_missing_landcover_columns_falls_back_to_old_behavior():
    # No in_agricultural_zone/forest_distance_km/water_distance_km at all —
    # must behave exactly as before landcover context existed.
    df = pd.DataFrame([_row(is_persistent=False, zone_type="other", confidence="n",
                             acq_date=pd.Timestamp("2026-11-15"))])
    out = classify(df)
    assert out.loc[0, "rule_label"] == "Likely Agricultural Burning"
