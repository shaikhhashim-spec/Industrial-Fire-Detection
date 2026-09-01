"""Model evaluation: accuracy/precision/recall/F1, confusion matrix, and
feature importance — computed on a held-out split, never fabricated.

CAVEAT, always surfaced alongside these numbers: the labels being scored
against are rule-derived ("weak labels"), not a human-verified ground-truth
dataset. This measures how well the model reproduces the rule engine, not
real-world classification accuracy.
"""
from __future__ import annotations

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)

CAVEAT = (
    "Model evaluation is based on prototype/weakly supervised (rule-derived) labels, "
    "not a human-verified ground-truth dataset. It measures agreement with the rule "
    "engine, not confirmed real-world classification accuracy. Larger validated "
    "datasets are required before this would be production-grade."
)


def evaluate(bundle: dict, split: dict) -> dict:
    clf, encoder, feature_cols = bundle["model"], bundle["encoder"], bundle["features"]
    X_test, y_test = split["X_test"], split["y_test"]

    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="weighted", zero_division=0)
    labels_present = sorted(set(y_test) | set(y_pred))
    label_names = [encoder.classes_[i] for i in labels_present]
    cm = confusion_matrix(y_test, y_pred, labels=labels_present)
    report = classification_report(y_test, y_pred, labels=labels_present, target_names=label_names, zero_division=0)
    importances = dict(sorted(zip(feature_cols, clf.feature_importances_.tolist(), strict=True), key=lambda kv: -kv[1]))

    return {
        "trained": True,
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "confusion_matrix": cm.tolist(),
        "confusion_labels": label_names,
        "classification_report": report,
        "feature_importances": importances,
        "n_train": len(split["X_train"]),
        "n_test": len(X_test),
        "version": bundle.get("version", "unknown"),
        "trained_at": bundle.get("trained_at", "unknown"),
        "n_total_available": bundle.get("n_total_available"),
        "caveat": CAVEAT,
    }
