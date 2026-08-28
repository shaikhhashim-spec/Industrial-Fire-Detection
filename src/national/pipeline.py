"""National-scale (India-wide) pipeline: latest FIRMS observations, cleaned,
grid-deduped into events, state-tagged, and given a simple risk tier.

Deliberately NOT the full regional pipeline: no OSM industrial join (that
would mean an expensive per-hotspot spatial query against national-scale
OSM data on every page load), no rule-based fire/flare/agri classification
(those categories are meaningless without industrial-zone context), and no
long history window (latest 24-48h only). This is the detection + spatial
distribution layer described in the platform's staged architecture — full
AI classification is reserved for the detailed Jharkhand-Odisha region.
"""
from __future__ import annotations

import pandas as pd

import config
from src import sample_data
from src.firms import fetch as firms_fetch
from src.national import states as national_states
from src.national import store as national_store
from src.processing import cleaning
from src.processing.persistence import compute_persistence
from src.utils.event_id import add_event_ids


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
    total = (persistence_score * w["persistence"] + frp_score * w["frp"] + conf_score * w["confidence"])
    df["risk_score"] = total.clip(lower=0, upper=100).round(1)

    def _level(score):
        for lo, hi, label in config.RISK_LEVELS:
            if lo <= score <= hi:
                return label
        return "LOW"

    df["risk_level"] = df["risk_score"].apply(_level)
    return df


def load_national_hotspots(demo_mode: bool, api_key: str | None = None) -> tuple[pd.DataFrame, str]:
    if not demo_mode:
        key = api_key or config.FIRMS_API_KEY
        if key:
            try:
                df = firms_fetch.fetch_country_hotspots(api_key=key, fallback_bbox=config.INDIA_BBOX)
                if not df.empty:
                    return df, "firms_live"
                print("[national.pipeline] FIRMS returned no rows, falling back")
            except firms_fetch.FirmsAuthError as exc:
                print(f"[national.pipeline] FIRMS auth error: {exc}")
            except Exception as exc:
                print(f"[national.pipeline] FIRMS fetch failed: {exc}")

        cached = sorted(config.CACHE_DIR.glob(f"firms_country-{config.NATIONAL_COUNTRY_CODE}_*.csv"))
        if cached:
            try:
                df = pd.read_csv(cached[-1])
                df["acq_date"] = pd.to_datetime(df["acq_date"])
                return df, "local_cache"
            except Exception as exc:
                print(f"[national.pipeline] local cache read failed: {exc}")

    return sample_data.generate_national_demo_hotspots(), "demo_data"


def run_national_pipeline(demo_mode: bool = False, api_key: str | None = None) -> dict:
    raw_df, hotspot_source = load_national_hotspots(demo_mode, api_key)
    if raw_df.empty:
        raise RuntimeError("No national hotspot data available from any source (live, cache, or demo).")

    clean_df, clean_report = cleaning.clean_hotspots(raw_df, bbox={})  # no region bbox — country endpoint already scoped
    if clean_df.empty:
        raise RuntimeError("All national rows were dropped during cleaning.")

    from src.ml.rules import normalize_confidence
    clean_df = normalize_confidence(clean_df)
    clean_df = national_states.assign_state(clean_df)

    used_history = False
    history_days_covered = 0
    if not demo_mode:
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
            risk_score=("risk_score", "max"), risk_level=("risk_level", "max"),
            satellites=("satellite", lambda s: sorted(set(s))),
        )
        .reset_index()
    )
    events = add_event_ids(events)

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

    return {
        "detail_df": clean_df,
        "events_df": events,
        "state_summary": state_summary,
        "hotspot_source": hotspot_source,
        "clean_report": clean_report,
        "n_observations": len(clean_df),
        "n_events": len(events),
        "used_accumulated_history": used_history,
        "history_days_covered": history_days_covered,
        "persistence_window_days": window_days,
    }


if __name__ == "__main__":
    info = run_national_pipeline(demo_mode=True)
    print(f"source: {info['hotspot_source']}")
    print(f"observations: {info['n_observations']}  events: {info['n_events']}")
    print(info["state_summary"].head(10))
