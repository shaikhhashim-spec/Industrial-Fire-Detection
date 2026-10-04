import pandas as pd

from src.incident_report import national_report, report_html


def test_national_report_preserves_observation_dates_evidence_and_source():
    event = {"event_id": "TH-A", "category": "Requires Verification", "risk_score": 70,
             "reasons": ["<script>unsafe</script>"], "risk_factors": [{"label": "Persistence", "points": 10}]}
    report = national_report(event, pd.DataFrame({"acq_date": ["2026-09-01", "2026-09-03"]}), "local_cache")
    assert "2026-09-01 to 2026-09-03" in report
    assert "Run source: local_cache" in report
    assert "human verification required" in report
    assert "<script>" not in report_html(report)
    assert "&lt;script&gt;" in report_html(report)


def test_missing_observations_are_unavailable():
    assert "Observed: Unavailable" in national_report({}, pd.DataFrame())
