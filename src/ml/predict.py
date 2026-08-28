"""Apply a trained model bundle to score every row: `ml_label` + `ml_confidence`
(the model's own probability for its top prediction). Falls back to the rule
label with a neutral confidence when no model is available yet."""
from __future__ import annotations

import joblib
import pandas as pd

import config


def load_model():
    if not config.MODEL_PATH.exists():
        return None
    try:
        return joblib.load(config.MODEL_PATH)
    except Exception:
        return None


def predict(df: pd.DataFrame, bundle: dict | None = None) -> pd.DataFrame:
    df = df.copy()
    bundle = bundle if bundle is not None else load_model()

    if not bundle:
        df["ml_label"] = df["rule_label"]
        df["ml_confidence"] = 0.5
        return df

    feature_cols = bundle["features"]
    X = df[[c for c in feature_cols if c in df.columns]].reindex(columns=feature_cols, fill_value=0).fillna(0)
    proba = bundle["model"].predict_proba(X)
    pred_idx = proba.argmax(axis=1)
    df["ml_label"] = bundle["encoder"].inverse_transform(pred_idx)
    df["ml_confidence"] = proba.max(axis=1).round(3)
    return df
