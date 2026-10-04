import pandas as pd

from src.processing.search import search_events


def test_words_match_across_fields_without_regex_or_accent_barriers():
    events = pd.DataFrame([
        {"event_id": "TH-[1]", "state": "Odisha", "category": "Industrial activity", "risk_level": "HIGH"},
        {"event_id": "TH-2", "place_name": "Cafe\u0301", "category": "Transient flare", "risk_level": "LOW"},
    ])
    assert search_events(events, "  ODISHA   high industrial ").event_id.tolist() == ["TH-[1]"]
    assert search_events(events, "[1]").event_id.tolist() == ["TH-[1]"]
    assert search_events(events, "cafe low").event_id.tolist() == ["TH-2"]
    assert search_events(events, "unknown").empty
    assert search_events(events, " ") is events


def test_numeric_grid_cells_and_missing_search_fields():
    events = pd.DataFrame({"grid_cell": [1234, None]})
    assert len(search_events(events, "123")) == 1
    assert search_events(pd.DataFrame({"frp": [12]}), "12").empty
    assert len(search_events(pd.DataFrame({"dominant_label": ["Industrial activity"]}), "industrial")) == 1
