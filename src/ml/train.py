"""Train a Random Forest on the rule engine's weak labels. These labels are
RULE-DERIVED, not human-verified ground truth — see evaluation.py's caveat,
which is surfaced in the dashboard every time evaluation metrics are shown.
"""
from __future__ import annotations

import datetime

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

import config
from src.ml.features import ML_FEATURE_COLUMNS

MIN_TRAINABLE_ROWS = 30


def train_classifier(df: pd.DataFrame, min_rows: int = MIN_TRAINABLE_ROWS):
    """Return (model_bundle, split, info). model_bundle is None if there
    isn't enough labeled data yet to train meaningfully — the caller should
    fall back to the rule labels rather than fabricate a trained model."""
    label_counts = df["rule_label"].value_counts()
    trainable_classes = label_counts[label_counts >= 2].index
    trainable = df[df["rule_label"].isin(trainable_classes)]

    if len(trainable) < min_rows or trainable["rule_label"].nunique() < 2:
        return None, None, {
            "trained": False,
            "reason": "not enough rule-labeled data yet to train a reliable classifier",
            "n_rows": len(df),
        }

    feature_cols = [c for c in ML_FEATURE_COLUMNS if c in trainable.columns]
    X = trainable[feature_cols].fillna(0)
    y = trainable["rule_label"]

    encoder = LabelEncoder()
    y_enc = encoder.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.25, random_state=42, stratify=y_enc if y.nunique() > 1 else None
    )

    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)
    clf.fit(X_train, y_train)

    now = datetime.datetime.now()
    version = f"RF-{now.strftime('%Y%m%d-%H%M%S')}"
    bundle = {
        "model": clf, "encoder": encoder, "features": feature_cols,
        "version": version, "trained_at": now.isoformat(timespec="seconds"),
        "n_train": len(X_train), "n_total_available": len(df),
    }
    joblib.dump(bundle, config.MODEL_PATH)

    split = {"X_train": X_train, "X_test": X_test, "y_train": y_train, "y_test": y_test}
    return bundle, split, {"trained": True, "n_train": len(X_train), "n_test": len(X_test), "version": version}
