"""Portable national incident reports from existing observations and evidence."""
from __future__ import annotations

import html
import pandas as pd


def national_report(event: dict, observations: pd.DataFrame, source: str = "unknown") -> str:
    dates = pd.to_datetime(observations.get("acq_date", pd.Series(dtype=str)), errors="coerce").dropna()
    observed = f"{dates.min().date()} to {dates.max().date()}" if not dates.empty else "Unavailable"
    lines = ["Thermal Intelligence: incident report", "Satellite screening; human verification required.",
             f"Event: {event.get('event_id', event.get('grid_cell'))}",
             f"Location: {event.get('place_name', '')}, {event.get('district', '')}, {event.get('state', '')}",
             f"Coordinates: {event.get('latitude')}, {event.get('longitude')}",
             f"Observed: {observed}", f"Run source: {source}",
             f"Classification: {event.get('category', 'Requires Verification')}",
             f"Risk: {event.get('risk_score')}/100 ({event.get('risk_level')})",
             f"Peak FRP: {event.get('max_frp')} MW", f"Days active: {event.get('persistence_days')}",
             "", "Evidence:"]
    for reason in event.get("reasons", []) or []:
        lines.append(f"- {reason}")
    lines += ["", "Risk factors:"]
    for factor in event.get("risk_factors", []) or []:
        lines.append(f"- {factor.get('label')}: {factor.get('points')} points; {factor.get('detail', '')}")
    lines += ["", "Satellite observations do not establish incident cause or confirm a fire.",
              "Risk scores are prototype heuristics. Model/rule agreement is not independent accuracy.",
              f"Report generated: {pd.Timestamp.now(tz='UTC').isoformat()}"]
    return "\n".join(lines)


def report_html(text: str) -> str:
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Incident report</title><style>body{font:16px/1.6 system-ui;max-width:850px;margin:32px auto;padding:0 20px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            f'<main><pre>{html.escape(text)}</pre></main></html>')
