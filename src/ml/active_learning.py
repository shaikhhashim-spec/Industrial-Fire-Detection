"""Compatibility entry point for legacy review dispositions.

Rejected, Confirmed and Reviewed are analyst workflow decisions, not independently
corroborated categories. They never change training labels. Independent reference
evaluation is separate from this function and trains no model.
"""
from __future__ import annotations

import pandas as pd

REJECTED_OVERRIDE_LABEL = "Sun Glint / False Positive"


def apply_review_overrides(df: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """Return an unchanged copy; review dispositions cannot establish truth.

    Independent evidence and category labels require a separate curated reference
    schema. This compatibility function intentionally accepts no training truth.
    """
    return df.copy() if df is not None else None
