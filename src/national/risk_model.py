"""Why an event is risky, and what to do about it.

Two separate things live here, deliberately kept apart:

1. **The risk decomposition.** The national risk score is a weighted sum of
   three components (persistence, fire radiative power, FIRMS confidence), so
   its breakdown is exact arithmetic, not an approximation or an attribution
   heuristic. `src/national/pipeline.py` records each component's contribution
   on the detection row that produced the event's score, and this module turns
   those numbers into ranked, plain-language factors.

2. **The model check.** A random forest is trained on this run's rule
   categories and asked to re-predict them. Agreement means the rule label is
   reproducible from the numeric features alone; disagreement flags an event
   whose label leans on something the features do not capture, and is worth a
   human look. The labels are rule-derived, so this measures self-consistency,
   never real-world accuracy: `MODEL_CAVEAT` says so wherever the numbers are
   shown.

`recommend_actions()` then maps category, risk tier and facility context to the
response an analyst would actually take. The actions are deliberately
conservative: satellite detection is not ground truth, so nothing here tells
anyone a fire is confirmed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

import config

MODEL_CAVEAT = (
    "The model is trained on this run's own rule labels, so agreement means the label is "
    "reproducible from the numbers alone. It is not a measure of real-world accuracy, and no "
    "detection here is a confirmed fire."
)

MIN_TRAINABLE_ROWS = 60

# Columns the pipeline writes alongside risk_score, one per weighted component.
COMPONENT_COLUMNS = {
    "risk_pts_persistence": "Persistence",
    "risk_pts_frp": "Heat output",
    "risk_pts_confidence": "Detection confidence",
}

MODEL_FEATURES = [
    "max_frp", "avg_frp", "persistence_days", "observation_count", "avg_confidence",
    "facility_km", "facility_high_heat", "night_share", "low_confidence_share", "detection_days",
]

# Categories whose response is "watch", not "respond". Splitting them out keeps
# the action list honest: most national detections are single unexplained
# pixels, and sending anyone to those would drown the real signal.
WATCH_ONLY = {"Sun Glint / False Positive", "Requires Verification", "Likely Agricultural Burning"}

URGENCY_BY_LEVEL = {
    "CRITICAL": "Now",
    "HIGH": "Today",
    "MODERATE": "This week",
    "LOW": "Monitor",
}


# --------------------------------------------------------------- factors --

def _factor_detail(name: str, row: dict, window_days: int) -> tuple[str, str]:
    """Returns (value, detail) for one risk component, in the units an analyst
    reads rather than the normalised 0-100 the score works in."""
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    if name == "Persistence":
        days = int(evidence.get("days") or row.get("persistence_days") or 0)
        return (
            f"{days} of {window_days} days",
            f"Heat came back on {days} separate days in the {window_days}-day window. "
            "A source that keeps reappearing is far more likely to be real and ongoing than a one-off pixel.",
        )
    if name == "Heat output":
        frp = float(evidence.get("maxFrp") or row.get("max_frp") or 0.0)
        vs = "above" if frp >= config.FRP_HIGH_MIN else "below"
        return (
            f"{frp:.1f} MW peak",
            f"Peak fire radiative power is {frp:.1f} MW, {vs} the {config.FRP_HIGH_MIN:.0f} MW "
            "threshold this project treats as a strong signal.",
        )
    conf = float(row.get("avg_confidence") or 0.0)
    low = float(evidence.get("lowConfidenceShare") or 0.0)
    return (
        f"{conf:.0f}/100",
        f"FIRMS rated these detections {conf:.0f} out of 100 on average"
        + (f", with {low:.0%} marked low confidence." if low else ".")
        + " Confidence reflects how cleanly the pixel separates from its background, not how dangerous it is.",
    )


def risk_factors(row: dict, window_days: int) -> list[dict]:
    """Rank the three weighted components by how many points each contributed
    to this event's score. Exact: the components sum to the score before it is
    clipped to 0-100."""
    parts = []
    for col, label in COMPONENT_COLUMNS.items():
        pts = row.get(col)
        if pts is None or (isinstance(pts, float) and not np.isfinite(pts)):
            continue
        parts.append((label, float(pts)))
    if not parts:
        return []
    total = sum(p for _, p in parts) or 1.0
    out = []
    for label, pts in sorted(parts, key=lambda p: p[1], reverse=True):
        value, detail = _factor_detail(label, row, window_days)
        out.append({
            "label": label,
            "points": round(pts, 1),
            "share": round(pts / total, 3),
            "value": value,
            "detail": detail,
        })
    return out


def risk_summary(row: dict, factors: list[dict]) -> str:
    """One sentence naming the tier and what drove it."""
    level = str(row.get("risk_level") or "LOW")
    score = float(row.get("risk_score") or 0.0)
    if not factors:
        return f"Scored {score:.0f} out of 100 ({level.lower()} risk)."
    lead = factors[0]
    tail = f" with {factors[1]['label'].lower()} next" if len(factors) > 1 else ""
    return (
        f"Scored {score:.0f} out of 100 ({level.lower()} risk), driven mainly by "
        f"{lead['label'].lower()} at {lead['value']}{tail}."
    )


# ---------------------------------------------------------------- actions --

def recommend_actions(row: dict) -> list[dict]:
    """What to do next, given the category, the risk tier and whether a mapped
    facility can account for the heat."""
    category = str(row.get("category") or "Requires Verification")
    level = str(row.get("risk_level") or "LOW").upper()
    urgency = URGENCY_BY_LEVEL.get(level, "Monitor")
    facility = row.get("facility") if isinstance(row.get("facility"), dict) else None
    state = row.get("state") or "the state"
    site = (facility or {}).get("name") or "the mapped site"
    kind = (facility or {}).get("kind") or "facility"
    corroborated = bool(row.get("corroborated", True))

    actions: list[dict] = []

    if category == "Likely Industrial Fire":
        actions = [
            {"step": f"Call the district fire control room for {state}", "urgency": urgency,
             "detail": f"Give the coordinates and ask whether an incident is already logged at {site}."},
            {"step": f"Contact the safety officer at {site}", "urgency": urgency,
             "detail": f"A {kind} this close to the pixel is the most likely source. Confirm whether this is "
                       "an incident or a planned operation before escalating further."},
            {"step": "Hold the event open until a ground answer comes back", "urgency": "Today",
             "detail": "Satellite detection is not confirmation. Do not close it on the next quiet overpass alone."},
        ]
    elif category == "Persistent Industrial Activity":
        actions = [
            {"step": f"Check this against {site}'s declared operating pattern", "urgency": "This week",
             "detail": f"Recurring heat at a mapped {kind} usually means normal operation. It is worth a "
                       "response only when the heat output breaks its own baseline."},
            {"step": "Watch for a step change in heat output", "urgency": "Monitor",
             "detail": "The useful alarm here is a departure from this site's own history, not the raw score."},
        ]
    elif category == "Transient Industrial Flare":
        actions = [
            {"step": f"Match against the flaring schedule for {site}", "urgency": "This week",
             "detail": "Intermittent heat at a refinery or gas site is usually permitted flaring. Log it against "
                       "the permit rather than treating it as an incident."},
            {"step": "Record the pattern for emissions reporting", "urgency": "Monitor",
             "detail": "Repeat flares are more useful as a trend than as individual alerts."},
        ]
    elif category == "Persistent Non-Industrial Thermal Source":
        actions = [
            {"step": "Task a ground survey of the coordinates", "urgency": urgency,
             "detail": "Recurring heat with nothing mapped nearby often turns out to be an unmapped kiln, a "
                       "landfill fire or a coal-seam fire, all of which keep burning until someone intervenes."},
            {"step": "Add what the survey finds to OpenStreetMap", "urgency": "This week",
             "detail": "Mapping the source once removes it from the unexplained queue on every future run."},
        ]
    elif category == "Likely Wildfire":
        actions = [
            {"step": f"Notify the forest division for {state}", "urgency": urgency,
             "detail": "Route this to the forest control room rather than the industrial fire service."},
            {"step": "Check the next overpass for spread", "urgency": "Today",
             "detail": "A growing cluster of adjacent pixels is the signal that matters."},
        ]
    elif category == "Likely Agricultural Burning":
        actions = [
            {"step": f"Route to the crop-residue burning cell for {state}", "urgency": "This week",
             "detail": "Seasonal stubble burning is an air-quality and enforcement matter, not a fire response."},
            {"step": "Do not dispatch a fire response", "urgency": "Monitor",
             "detail": "Treating seasonal burning as an incident buries the industrial signal this system exists to find."},
        ]
    elif category == "Sun Glint / False Positive":
        actions = [
            {"step": "No response", "urgency": "Monitor",
             "detail": "A single low-confidence daytime pixel with very low heat is the classic glint signature."},
        ]
    else:
        actions = [
            {"step": "Wait for the next satellite overpass", "urgency": "Monitor",
             "detail": "A second detection is what separates a real source from sensor noise. The globe's "
                       "next-overpass panel gives the time."},
            {"step": "Request high-resolution imagery for the coordinates", "urgency": "This week",
             "detail": "One unexplained pixel is not worth a field visit, but it is worth a look at imagery."},
        ]

    if not corroborated:
        actions.insert(0, {
            "step": "Treat as unconfirmed", "urgency": "Monitor",
            "detail": "One pixel on one pass, with no repeat and no mapped facility. Everything below assumes "
                      "it survives a second detection.",
        })
    if level == "CRITICAL" and category not in WATCH_ONLY:
        actions.insert(0, {
            "step": "Escalate now and record who acknowledged it", "urgency": "Now",
            "detail": f"This is in the top risk tier. Dispatch the alert, and if nobody acknowledges within "
                      f"{config.ALERT_ESCALATE_AFTER_MIN} minutes the Alerts page will offer a voice call.",
        })
    return actions


# ------------------------------------------------------------ model check --

def _feature_frame(ev: pd.DataFrame) -> pd.DataFrame:
    """Numeric view of each event, built only from things the satellite and the
    open reference data actually measured."""
    f = pd.DataFrame(index=ev.index)
    f["max_frp"] = pd.to_numeric(ev.get("max_frp"), errors="coerce").fillna(0.0)
    f["avg_frp"] = pd.to_numeric(ev.get("avg_frp"), errors="coerce").fillna(0.0)
    f["persistence_days"] = pd.to_numeric(ev.get("persistence_days"), errors="coerce").fillna(0.0)
    f["observation_count"] = pd.to_numeric(ev.get("observation_count"), errors="coerce").fillna(0.0)
    f["avg_confidence"] = pd.to_numeric(ev.get("avg_confidence"), errors="coerce").fillna(0.0)

    facility = ev["facility"] if "facility" in ev.columns else pd.Series([None] * len(ev), index=ev.index)
    # 99 km stands for "nothing mapped nearby": a real distance would imply a
    # precision the reference data does not have out there.
    f["facility_km"] = [float(x.get("distanceKm", 99.0)) if isinstance(x, dict) else 99.0 for x in facility]
    from src.national.context import HIGH_HEAT_KINDS
    f["facility_high_heat"] = [
        1.0 if isinstance(x, dict) and x.get("kind") in HIGH_HEAT_KINDS else 0.0 for x in facility
    ]

    evidence = ev["evidence"] if "evidence" in ev.columns else pd.Series([None] * len(ev), index=ev.index)

    def _ev(key: str, default: float) -> list[float]:
        return [float(x.get(key, default)) if isinstance(x, dict) else default for x in evidence]

    detections = np.array(_ev("detections", 1.0))
    nights = np.array(_ev("nightPasses", 0.0))
    f["night_share"] = np.divide(nights, np.maximum(detections, 1.0))
    f["low_confidence_share"] = _ev("lowConfidenceShare", 0.0)
    f["detection_days"] = _ev("days", 1.0)
    return f[MODEL_FEATURES]


def validate_categories(ev: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    """Re-predict the rule categories from the numeric features.

    Returns (predicted_label, predicted_confidence, info). When there is too
    little data to train honestly, both series are empty and info explains why,
    rather than a model being fabricated to fill the panel.
    """
    if ev is None or ev.empty or "category" not in ev.columns:
        return pd.Series(dtype=str), pd.Series(dtype=float), {
            "trained": False, "reason": "no classified events in this run", "caveat": MODEL_CAVEAT}

    counts = ev["category"].value_counts()
    trainable = ev[ev["category"].isin(counts[counts >= 2].index)]
    if len(trainable) < MIN_TRAINABLE_ROWS or trainable["category"].nunique() < 2:
        return pd.Series(dtype=str), pd.Series(dtype=float), {
            "trained": False,
            "reason": f"only {len(trainable)} events across {trainable['category'].nunique()} categories, "
                      f"below the {MIN_TRAINABLE_ROWS}-row minimum",
            "caveat": MODEL_CAVEAT,
        }

    X_all = _feature_frame(ev)
    X = X_all.loc[trainable.index]
    encoder = LabelEncoder()
    y = encoder.fit_transform(trainable["category"])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, class_weight="balanced")
    clf.fit(X_train, y_train)
    holdout = float(accuracy_score(y_test, clf.predict(X_test)))

    proba = clf.predict_proba(X_all)
    best = proba.argmax(axis=1)
    labels = pd.Series(encoder.inverse_transform(best), index=ev.index)
    confidence = pd.Series(proba.max(axis=1), index=ev.index)

    importances = dict(sorted(
        zip(MODEL_FEATURES, (round(float(v), 4) for v in clf.feature_importances_)),
        key=lambda kv: kv[1], reverse=True,
    ))
    info = {
        "trained": True,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "holdout_agreement": round(holdout, 4),
        "classes": list(encoder.classes_),
        "feature_importances": importances,
        "caveat": MODEL_CAVEAT,
    }
    return labels, confidence, info


# ------------------------------------------------------------- entrypoint --

def enrich_risk(ev: pd.DataFrame, window_days: int) -> tuple[pd.DataFrame, dict]:
    """Add the risk decomposition, the model check, the priority rank and the
    recommended actions to an already-classified events frame."""
    if ev is None or ev.empty:
        return ev, {"trained": False, "reason": "no events", "caveat": MODEL_CAVEAT}

    ev = ev.copy()
    labels, confidence, info = validate_categories(ev)

    factors, summaries, actions, checks = [], [], [], []
    for _, row in ev.iterrows():
        r = row.to_dict()
        fs = risk_factors(r, window_days)
        factors.append(fs)
        summaries.append(risk_summary(r, fs))
        actions.append(recommend_actions(r))
        if labels.empty:
            checks.append(None)
        else:
            predicted = str(labels.loc[row.name])
            checks.append({
                "label": predicted,
                "confidence": round(float(confidence.loc[row.name]), 3),
                "agrees": predicted == str(r.get("category")),
                "holdoutAgreement": info.get("holdout_agreement"),
                "caveat": MODEL_CAVEAT,
            })

    ev["risk_factors"] = factors
    ev["risk_summary"] = summaries
    ev["actions"] = actions
    ev["model_check"] = checks
    # Rank once, here, so the dashboard queue and the globe queue agree.
    ev["priority"] = ev["risk_score"].rank(method="first", ascending=False).astype(int)
    return ev, info
