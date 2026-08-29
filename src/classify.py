"""Backend/AI orchestrator — the pipeline stage every other layer (dashboard,
future API, batch jobs) calls. Combines persistence tracking, feature
engineering, rule-based classification, the ML validation layer, risk
scoring, and status assignment into one call, and persists the result.

Input contract: `df` must already carry raw FIRMS columns (latitude,
longitude, acq_date, acq_time, satellite, frp, confidence, ...) PLUS
`zone_type` (+ ideally industrial_distance_km/mine_distance_km) attached by
the geospatial join stage (src/geospatial/spatial_join.py). This module does
not fetch anything and does not query OSM.
"""
from __future__ import annotations

import pandas as pd

import config
from src import store
from src.ml import evaluation, features, predict, rules, train
from src.processing import persistence
from src.risk import scoring as risk_scoring
from src.risk.anomaly import compute_frp_anomaly
from src.utils import status as status_utils
from src.utils.event_id import add_event_ids

REQUIRED_INPUT_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "frp", "confidence", "zone_type"}


def classify_hotspots(df: pd.DataFrame, demo_mode: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Returns (detail_df, cluster_df, info).

    detail_df  — one row per detection, fully classified and risk-scored.
    cluster_df — one row per ~1km grid cell (the persistent-source view
                 used for alerts and the Top Persistent Clusters table),
                 with a dominant classification, risk, and lifecycle status.
    info       — ML metrics (see src/ml/evaluation.py) plus row/cluster counts.

    demo_mode=True keeps this call fully self-contained: it neither reads
    nor writes the shared SQLite store, so synthetic demo detections can
    never leak into (or be diluted by) the real accumulated history, and
    vice versa. The fixed demo dataset already spans its own window on its
    own, so there's nothing to extend it with anyway.
    """
    missing = REQUIRED_INPUT_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"classify_hotspots() is missing required input columns {sorted(missing)}. "
            "zone_type must already be attached by the geospatial join stage."
        )
    if df.empty:
        raise ValueError("classify_hotspots() received an empty dataframe.")

    df = df.copy()
    df["acq_date"] = pd.to_datetime(df["acq_date"])

    if not demo_mode:
        # Extend the persistence window with previously stored history
        # (records the live fetch no longer serves), capped back to the
        # same span a single fetch would cover so "N days in the window"
        # doesn't drift as the store grows across repeated calls.
        history = store.load_input_history()
        if not history.empty:
            combined = pd.concat(
                [history, df[[c for c in store.INPUT_COLUMNS if c in df.columns]]], ignore_index=True
            ).drop_duplicates(subset=store.NATURAL_KEY, keep="last")
            cutoff = combined["acq_date"].max() - pd.Timedelta(days=config.FIRMS_TOTAL_DAYS)
            df = combined[combined["acq_date"] > cutoff].reset_index(drop=True)

    df = persistence.compute_persistence(df)
    cluster_summary = persistence.build_cluster_summary(df)

    df = features.build_features(df, cluster_summary)
    df = rules.classify(df)

    bundle, split, train_info = train.train_classifier(df)
    if bundle:
        df = predict.predict(df, bundle)
        ml_metrics = evaluation.evaluate(bundle, split)
    else:
        df = predict.predict(df, None)
        ml_metrics = train_info

    df = risk_scoring.compute_risk(df)
    cluster_df = _build_cluster_view(df, cluster_summary)

    if not demo_mode:
        store.upsert(df)

    info = {"ml_metrics": ml_metrics, "n_detections": len(df), "n_clusters": len(cluster_df), "demo_mode": demo_mode}
    return df, cluster_df, info


def _build_cluster_view(df: pd.DataFrame, cluster_summary: pd.DataFrame) -> pd.DataFrame:
    if cluster_summary.empty:
        return cluster_summary
    agg_spec = dict(
        dominant_label=("rule_label", lambda s: s.mode().iat[0]),
        risk_score=("risk_score", "max"),
        zone_type=("zone_type", lambda s: s.mode().iat[0]),
        industrial_distance_km=("industrial_distance_km", "min"),
        mine_distance_km=("mine_distance_km", "min"),
    )
    if "zone_kind" in df.columns:
        agg_spec["zone_kind"] = ("zone_kind", lambda s: s.mode().iat[0] if not s.mode().empty else "other")
    if "power_distance_km" in df.columns:
        agg_spec["power_distance_km"] = ("power_distance_km", "min")
    if "forest_distance_km" in df.columns:
        agg_spec["forest_distance_km"] = ("forest_distance_km", "min")
    if "water_distance_km" in df.columns:
        agg_spec["water_distance_km"] = ("water_distance_km", "min")
    if "in_agricultural_zone" in df.columns:
        agg_spec["in_agricultural_zone"] = ("in_agricultural_zone", "any")
    if "ml_confidence" in df.columns:
        agg_spec["ml_confidence"] = ("ml_confidence", "mean")
    if "confidence_numeric" in df.columns:
        agg_spec["confidence_numeric"] = ("confidence_numeric", "mean")
    agg = df.groupby("grid_cell").agg(**agg_spec).reset_index()
    cluster_df = cluster_summary.merge(agg, on="grid_cell", how="left")
    cluster_df["risk_level"] = cluster_df["risk_score"].apply(risk_scoring.risk_level)
    if "ml_confidence" in cluster_df.columns:
        cluster_df["ai_confidence"] = cluster_df["ml_confidence"].apply(
            lambda c: round(float(c) * 100, 1) if pd.notna(c) and float(c) <= 1.0 else round(float(c), 1) if pd.notna(c) else 85.0
        )
    elif "avg_confidence" in cluster_df.columns:
        cluster_df["ai_confidence"] = cluster_df["avg_confidence"].apply(
            lambda c: round(float(c), 1) if pd.notna(c) else 85.0
        )
    else:
        cluster_df["ai_confidence"] = 85.0
    cluster_df = status_utils.assign_status(cluster_df)
    cluster_df = add_event_ids(cluster_df)
    anomaly = compute_frp_anomaly(df)
    if not anomaly.empty:
        cluster_df = cluster_df.merge(anomaly, on="grid_cell", how="left")
        cluster_df["is_anomalous"] = cluster_df["is_anomalous"].fillna(False)
    return cluster_df


# Alias matching the roadmap's original literal deliverable name.
classify_hotspot = classify_hotspots
