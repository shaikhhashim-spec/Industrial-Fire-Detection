"""Literal, multi-word event search shared by dashboard views."""
from __future__ import annotations

import unicodedata

import pandas as pd

SEARCH_FIELDS = (
    "event_id", "id", "grid_cell", "state", "district", "country", "region",
    "place", "place_name", "facility", "category", "classification", "rule_label", "dominant_label",
    "risk_level", "status",
)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    return "".join(char for char in text if not unicodedata.combining(char))


def search_events(events: pd.DataFrame, query: str) -> pd.DataFrame:
    terms = _normalize(query).split()
    if not terms or events.empty:
        return events
    columns = [column for column in SEARCH_FIELDS if column in events]
    if not columns:
        return events.iloc[0:0]
    text = events[columns].fillna("").astype(str).agg(" ".join, axis=1).map(_normalize)
    mask = pd.Series(True, index=events.index)
    for term in terms:
        mask &= text.str.contains(term, regex=False)
    return events.loc[mask]
