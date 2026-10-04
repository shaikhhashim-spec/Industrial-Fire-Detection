import json

import pytest

from scripts.demo_preflight import audit, prepare


def payload(**overrides):
    event = {"id": "TH-A", "latitude": 22.8, "longitude": 86.18,
             "acqDate": "2026-09-01", "riskScore": 70, "category": "Requires Verification",
             "reasons": ["<script>unsafe</script>"], **overrides}
    return {"meta": {"source": "local_cache"}, "events": [event]}


@pytest.mark.parametrize("changes", [{"synthetic": True}, {"latitude": 91}, {"longitude": None}, {"acqDate": "2999-01-01"}])
def test_preflight_rejects_unusable_or_synthetic_exports(changes):
    with pytest.raises((ValueError, TypeError)):
        audit(payload(**changes))


@pytest.mark.parametrize("data", [None, [], {"meta": None}, {"meta": {"source": "firms_live"}, "events": [None]}])
def test_bad_export_structure_gives_clear_error(data):
    with pytest.raises(ValueError):
        audit(data)


def test_artifacts_keep_pending_references_unverified_and_escape_report(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")
    result = prepare(path, tmp_path / "packet")
    assert len(result["sha256"]) == 64
    assert result["observationEnd"] == "2026-09-01"
    references = json.loads((tmp_path / "packet/references-pending.json").read_text())
    assert references[0]["independentlyCorroborated"] is False
    assert references[0]["label"] == "unresolved"
    report = (tmp_path / "packet/sample-incident.html").read_text()
    assert "<script>unsafe</script>" not in report
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in report
