"""National-scale (India-wide) pipeline: latest FIRMS observations, cleaned,
grid-deduped into events, state-tagged, and given a simple risk tier.

Deliberately NOT the full regional pipeline: no OSM industrial join (that
would mean an expensive per-hotspot spatial query against national-scale
OSM data on every page load), no rule-based fire/flare/agri classification
(those categories are meaningless without industrial-zone context), and no
long history window (latest 24-48h only). This is the detection + spatial
distribution layer described in the platform's staged architecture — full
AI classification is reserved for the detailed Jharkhand-Odisha region.

Live data only: FIRMS, or the real history stored by earlier live runs.
"""
from __future__ import annotations

import pandas as pd

import config
from src.firms import fetch as firms_fetch
from src.national import context as national_context
from src.national import snapshot as national_snapshot
from src.national import risk_model as national_risk_model
from src.national import states as national_states
from src.national import store as national_store
from src.processing import cleaning
from src.processing.persistence import compute_persistence
from src.utils.event_id import add_event_ids


def _risk_level(score: float) -> str:
    """The config band a score falls in. Shared, so a detection and the event it
    belongs to can never disagree about what 88 out of 100 means."""
    for lo, hi, label in config.RISK_LEVELS:
        if lo <= score <= hi:
            return label
    return "LOW"


def _national_risk(df: pd.DataFrame, window_days: int | None = None) -> pd.DataFrame:
    """Simple risk tier using only FRP + confidence + persistence — no
    industrial-proximity component, since that requires the OSM join this
    pipeline deliberately skips. A distinct, simpler model from the full
    regional risk score (config.RISK_WEIGHTS). `window_days` normalizes the
    persistence component and should match whatever window persistence was
    actually computed over (the fresh 2-day batch, or accumulated history)."""
    df = df.copy()
    w = config.NATIONAL_RISK_WEIGHTS
    window_days = window_days or config.NATIONAL_DAY_RANGE
    persistence_score = (df["persistence_days"] / max(window_days, 1) * 100).clip(upper=100)
    frp_score = (df["frp"] / config.FRP_HIGH_MIN * 100).clip(upper=100)
    conf_score = df["confidence_numeric"].clip(lower=0, upper=100)
    # Each component's weighted points are kept, so the score can be broken back
    # down exactly rather than attributed after the fact (see national/risk_model.py).
    df["risk_pts_persistence"] = (persistence_score * w["persistence"]).round(2)
    df["risk_pts_frp"] = (frp_score * w["frp"]).round(2)
    df["risk_pts_confidence"] = (conf_score * w["confidence"]).round(2)
    total = df["risk_pts_persistence"] + df["risk_pts_frp"] + df["risk_pts_confidence"]
    df["risk_score"] = total.clip(lower=0, upper=100).round(1)

    df["risk_level"] = df["risk_score"].apply(_risk_level)
    return df


def load_national_hotspots(api_key: str | None = None) -> tuple[pd.DataFrame, str]:
    """Live FIRMS for India; if that fails, the real history already stored
    from earlier live runs. Never synthetic — raises when neither exists."""
    # Rows from the old demo generator must never count as history.
    national_store.purge_demo_rows()
    key = api_key or config.FIRMS_API_KEY
    if key:
        try:
            # A cold store backfills a full history window (6 five-day
            # requests per satellite) so persistence is meaningful from the
            # very first live run; after that each run tops up 2 days.
            cold = national_store.days_covered() < config.NATIONAL_HISTORY_DAYS // 3
            total_days = config.NATIONAL_HISTORY_DAYS if cold else config.NATIONAL_DAY_RANGE
            df = firms_fetch.fetch_country_hotspots(
                api_key=key, fallback_bbox=config.INDIA_BBOX, total_days=total_days,
            )
            if not df.empty:
                return df, "firms_live"
            print("[national.pipeline] FIRMS returned no rows, using stored live history")
        except firms_fetch.FirmsAuthError as exc:
            print(f"[national.pipeline] FIRMS auth error: {exc}")
        except Exception as exc:
            print(f"[national.pipeline] FIRMS fetch failed: {exc}")

    history = national_store.load_history(days=config.NATIONAL_HISTORY_DAYS)
    if not history.empty:
        return history, "local_cache"
    raise RuntimeError(
        "No live FIRMS data: the API is unreachable (or FIRMS_API_KEY is missing from .env) "
        "and no earlier live run is stored."
    )


def run_national_pipeline(api_key: str | None = None) -> dict:
    raw_df, hotspot_source = load_national_hotspots(api_key)
    if raw_df.empty:
        raise RuntimeError("FIRMS returned no detections for India.")

    clean_df, clean_report = cleaning.clean_hotspots(raw_df, bbox={})  # no region bbox — country endpoint already scoped
    if clean_df.empty:
        raise RuntimeError("All national rows were dropped during cleaning.")

    from src.ml.rules import normalize_confidence
    clean_df = normalize_confidence(clean_df)
    clean_df = national_states.assign_state(clean_df)

    # India only: the FIRMS request is a bounding box, so it also returns the
    # sea, Pakistan, Nepal, Bangladesh, Myanmar and Tibet. Keep detections that
    # fall inside a real Indian state/UT boundary.
    outside = clean_df["state"].isna()
    clean_report["dropped_outside_india"] = int(outside.sum())
    clean_df = clean_df[~outside].reset_index(drop=True)
    if clean_df.empty:
        raise RuntimeError("No detections fall inside India's state boundaries for this window.")

    used_history = False
    history_days_covered = 0
    national_store.upsert(clean_df)
    history = national_store.load_history(days=config.NATIONAL_HISTORY_DAYS)
    if not history.empty:
        clean_df = history.drop_duplicates(subset=national_store.NATURAL_KEY, keep="last").reset_index(drop=True)
        used_history = True
        history_days_covered = national_store.days_covered()

    min_days = config.NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY if used_history else config.NATIONAL_PERSISTENCE_MIN_DAYS
    window_days = config.NATIONAL_HISTORY_DAYS if used_history else config.NATIONAL_DAY_RANGE
    clean_df = compute_persistence(clean_df, min_days=min_days)
    clean_df = _national_risk(clean_df, window_days=window_days)

    # "Events" = one row per grid cell (deduped observation groups), per the
    # platform's observation-vs-event distinction.
    events = (
        clean_df.groupby("grid_cell")
        .agg(
            state=("state", lambda s: s.mode().iat[0] if not s.mode().empty else None),
            latitude=("latitude", "mean"), longitude=("longitude", "mean"),
            observation_count=("frp", "size"), avg_frp=("frp", "mean"), max_frp=("frp", "max"),
            avg_confidence=("confidence_numeric", "mean"),
            persistence_days=("persistence_days", "max"),
            is_persistent=("is_persistent", "max"),
            risk_score=("risk_score", "max"),
            satellites=("satellite", lambda s: sorted(set(s))),
        )
        .reset_index()
    )
    # The event's score is the highest of its detections, so its tier has to be
    # read back off that score. Aggregating the tier string directly took the
    # alphabetical maximum, which quietly turned a 90-point event into
    # "MODERATE" and emptied the critical queue.
    events["risk_level"] = events["risk_score"].apply(_risk_level)
    events = add_event_ids(events)

    # Carry the risk components from the detection that actually set each
    # event's score (the score is a max over detections, so the breakdown has
    # to come from that same row to add up).
    component_cols = ["risk_pts_persistence", "risk_pts_frp", "risk_pts_confidence"]
    top_rows = clean_df.loc[clean_df.groupby("grid_cell")["risk_score"].idxmax(), ["grid_cell", *component_cols]]
    events = events.merge(top_rows, on="grid_cell", how="left")

    # Why each point is there: nearest facility, town, evidence and category.
    events = national_context.enrich_events(events, clean_df)
    # Why it is risky, whether the model agrees, and what to do about it.
    events, model_info = national_risk_model.enrich_risk(events, window_days)

    state_summary = (
        clean_df.groupby("state", dropna=True)
        .agg(
            hotspots=("frp", "size"),
            persistent_sources=("is_persistent", "sum"),
            high_risk=("risk_level", lambda s: (s == "HIGH").sum()),
            critical=("risk_level", lambda s: (s == "CRITICAL").sum()),
        )
        .reset_index()
        .sort_values("hotspots", ascending=False)
    )

    info = {
        "detail_df": clean_df,
        "events_df": events,
        "state_summary": state_summary,
        "hotspot_source": hotspot_source,
        "clean_report": clean_report,
        "dropped_outside_india": clean_report["dropped_outside_india"],
        "n_observations": len(clean_df),
        "n_events": len(events),
        "used_accumulated_history": used_history,
        "history_days_covered": history_days_covered,
        "persistence_window_days": window_days,
        "model_info": model_info,
        "run_at": pd.Timestamp.now(),
    }
    # One live run feeds everything: the dashboard adopts this snapshot on
    # startup, and the 3D globe is exported from the same run.
    national_snapshot.save(info)
    return info


if __name__ == "__main__":
    info = run_national_pipeline()
    print(f"source: {info['hotspot_source']}")
    print(f"observations: {info['n_observations']}  events: {info['n_events']}")
    print(info["state_summary"].head(10))
