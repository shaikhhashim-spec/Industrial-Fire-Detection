import pandas as pd

from src.ml.active_learning import apply_review_overrides


def _df():
    return pd.DataFrame({
        "grid_cell": ["A", "B", "C"],
        "rule_label": ["Requires Verification", "Requires Verification", "Likely Industrial Fire"],
    })


def test_rejected_overrides_to_sun_glint():
    reviews = pd.DataFrame({"grid_cell": ["A"], "decision": ["Rejected"]})
    out = apply_review_overrides(_df(), reviews)
    assert out.loc[out["grid_cell"] == "A", "rule_label"].iat[0] == "Sun Glint / False Positive"


def test_confirmed_and_reviewed_leave_label_untouched():
    reviews = pd.DataFrame({"grid_cell": ["A", "B"], "decision": ["Confirmed", "Reviewed"]})
    out = apply_review_overrides(_df(), reviews)
    assert list(out["rule_label"]) == ["Requires Verification", "Requires Verification", "Likely Industrial Fire"]


def test_original_dataframe_not_mutated():
    df = _df()
    reviews = pd.DataFrame({"grid_cell": ["A"], "decision": ["Rejected"]})
    apply_review_overrides(df, reviews)
    assert df.loc[df["grid_cell"] == "A", "rule_label"].iat[0] == "Requires Verification"


def test_empty_reviews_returns_unchanged_copy():
    df = _df()
    out = apply_review_overrides(df, pd.DataFrame())
    assert list(out["rule_label"]) == list(df["rule_label"])
    assert out is not df


def test_empty_df_passthrough():
    empty = pd.DataFrame()
    assert apply_review_overrides(empty, pd.DataFrame({"grid_cell": ["A"], "decision": ["Rejected"]})).empty
