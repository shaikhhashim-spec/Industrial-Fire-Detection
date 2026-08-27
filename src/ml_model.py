"""ML validation layer (v2): train a Random Forest on the rule-based (v1)
labels using only the numeric/categorical features, then report accuracy and
feature importance. Framed in the pitch as "an additional layer we're
validating" against the explainable rule engine, not a replacement for it.
"""
from __future__ import annotations

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

import config

FEATURE_COLUMNS = ["frp", "confidence_numeric", "persistence_days", "brightness", "zone_type_encoded"]


def _prep_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["zone_type_encoded"] = (df["zone_type"] == "industrial").astype(int)
    if "brightness" not in df.columns:
        df["brightness"] = df.get("bright_ti4", 0.0)
    return df


def train_and_predict(df: pd.DataFrame, min_rows: int = 30) -> tuple[pd.DataFrame, dict]:
    """Train on rule_label, add `ml_label` predictions for every row, and
    return a metrics dict (accuracy, feature_importances, class counts).

    If there isn't enough data or label diversity to train meaningfully,
    ml_label falls back to rule_label and metrics reports that.
    """
    df = _prep_features(df)

    label_counts = df["rule_label"].value_counts()
    trainable_classes = label_counts[label_counts >= 2].index
    trainable = df[df["rule_label"].isin(trainable_classes)]

    if len(trainable) < min_rows or trainable["rule_label"].nunique() < 2:
        df["ml_label"] = df["rule_label"]
        return df, {
            "trained": False,
            "reason": "not enough labeled data yet to train a reliable classifier",
            "n_rows": len(df),
        }

    X = trainable[FEATURE_COLUMNS].fillna(0)
    y = trainable["rule_label"]

    encoder = LabelEncoder()
    y_enc = encoder.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.25, random_state=42, stratify=y_enc if y.nunique() > 1 else None
    )

    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=encoder.classes_, zero_division=0)

    importances = dict(zip(FEATURE_COLUMNS, clf.feature_importances_.tolist()))

    all_X = df[FEATURE_COLUMNS].fillna(0)
    df["ml_label"] = encoder.inverse_transform(clf.predict(all_X))

    joblib.dump({"model": clf, "encoder": encoder, "features": FEATURE_COLUMNS}, config.MODEL_PATH)

    metrics = {
        "trained": True,
        "accuracy": accuracy,
        "feature_importances": importances,
        "classification_report": report,
        "n_train": len(X_train),
        "n_test": len(X_test),
    }
    return df, metrics
