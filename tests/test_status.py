import pandas as pd

import config
from src.utils.status import STATUS_CRITICAL, STATUS_INACTIVE, assign_status


def _row(**overrides):
    base = dict(
        risk_score=10,
        is_persistent=False,
        last_detected=pd.Timestamp("2026-09-25"),
        first_detected=pd.Timestamp("2026-09-25"),
        detection_count=1,
    )
    base.update(overrides)
    return base


def test_empty_df_gets_empty_status_column():
    out = assign_status(pd.DataFrame())
    assert list(out["status"]) == []


def test_high_risk_score_is_critical_when_recently_seen():
    df = pd.DataFrame([_row(risk_score=90, last_detected=pd.Timestamp("2026-09-25"))])
    out = assign_status(df)
    assert out["status"].iloc[0] == STATUS_CRITICAL


def test_high_risk_score_but_long_silent_is_inactive_not_critical():
    """A grid cell that hasn't fired in weeks must not keep reading CRITICAL
    off a risk_score that reflects only its history."""
    stale_days = config.STATUS_INACTIVE_AFTER_DAYS + 5
    df = pd.DataFrame([
        _row(
            risk_score=90,
            last_detected=pd.Timestamp("2026-09-25") - pd.Timedelta(days=stale_days),
        )
    ])
    now_anchor = pd.DataFrame([_row(risk_score=1, last_detected=pd.Timestamp("2026-09-25"))])
    out = assign_status(pd.concat([df, now_anchor], ignore_index=True))
    assert out["status"].iloc[0] == STATUS_INACTIVE
