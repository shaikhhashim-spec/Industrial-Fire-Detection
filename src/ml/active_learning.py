"""A lightweight active-learning loop: fold analyst review decisions from
the Validation queue (`analyst_reviews` in SQLite) back into the training
labels before retraining, rather than a scheduled/automatic retrain.

Only "Rejected" is actionable as a label correction — the analyst
explicitly said a "Requires Verification" event isn't real, which maps
cleanly onto the existing "Sun Glint / False Positive" category.
"Confirmed"/"Reviewed" reinforce the rule engine's existing label rather
than changing it, so they don't need a training-label override (there is
no real "this is definitely industrial fire, not X" signal to encode
without asking the analyst to pick a category, which the Validation queue
doesn't currently do).
"""
from __future__ import annotations

import pandas as pd

REJECTED_OVERRIDE_LABEL = "Sun Glint / False Positive"


def apply_review_overrides(df: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of `df` with `rule_label` overridden to
    REJECTED_OVERRIDE_LABEL for every grid cell an analyst marked
    "Rejected". Safe to call with empty/missing inputs — returns `df`
    unchanged (as a copy) in that case."""
    if df is None or df.empty:
        return df
    df = df.copy()
    if reviews is None or reviews.empty or "grid_cell" not in reviews.columns:
        return df
    rejected_cells = set(reviews.loc[reviews["decision"] == "Rejected", "grid_cell"])
    if rejected_cells and "grid_cell" in df.columns:
        df.loc[df["grid_cell"].isin(rejected_cells), "rule_label"] = REJECTED_OVERRIDE_LABEL
    return df
