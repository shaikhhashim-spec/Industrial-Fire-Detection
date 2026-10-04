"""Audit an existing FIRMS export and prepare judging artifacts without network calls."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(payload: dict) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        raise ValueError("Expected an export object with source metadata")
    meta = payload.get("meta", {})
    events = payload.get("events")
    if meta.get("source") not in {"firms_live", "local_cache", "mixed"}:
        raise ValueError("Export must declare a real FIRMS source")
    if not isinstance(events, list) or not events:
        raise ValueError("Export contains no events")
    dates, ids = [], set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Expected event objects")
        identity = event.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in ids:
            raise ValueError("Event IDs must be present and unique")
        ids.add(identity)
        if event.get("synthetic") is True:
            raise ValueError(f"Synthetic event in export: {identity}")
        for key, bound in (("latitude", 90), ("longitude", 180)):
            value = event.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > bound:
                raise ValueError(f"Invalid {key} for {identity}")
        date = dt.date.fromisoformat(event["acqDate"])
        if date > dt.datetime.now(dt.timezone.utc).date():
            raise ValueError(f"Future observation date for {identity}")
        dates.append(date)
    return {"source": meta["source"], "generatedAt": meta.get("generatedAt"),
            "events": len(events), "observationStart": min(dates).isoformat(),
            "observationEnd": max(dates).isoformat(),
            "ageDays": (dt.datetime.now(dt.timezone.utc).date() - max(dates)).days,
            "checks": "Schema, unique IDs, coordinates, dates, declared source and synthetic flags",
            "limitation": "Local integrity audit only; upstream authenticity and incident causes are not independently verified."}


def prepare(input_path: Path, output_dir: Path) -> dict:
    body = input_path.read_bytes()
    payload = json.loads(body)
    result = audit(payload)
    result["sha256"] = hashlib.sha256(body).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cache-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    # Select diverse labels before filling the small review queue.
    selected, categories = [], set()
    ordered = sorted(payload["events"], key=lambda e: e.get("riskScore", 0), reverse=True)
    for event in ordered:
        if event.get("category") not in categories:
            selected.append(event)
            categories.add(event.get("category"))
        if len(selected) >= 12:
            break
    selected_ids = {event["id"] for event in selected}
    selected.extend(event for event in ordered if event["id"] not in selected_ids)
    selected = selected[:12]
    references = [{"eventId": event["id"], "siteId": f"{event['latitude']:.4f},{event['longitude']:.4f}",
                   "observedAt": f"{event['acqDate']}T00:00:00Z", "label": "unresolved",
                   "independentlyCorroborated": False, "referenceType": "", "supportingSources": [],
                   "verifiedBy": "", "verifiedAt": None, "notes": "Pending independent evidence review"}
                  for event in selected]
    (output_dir / "references-pending.json").write_text(json.dumps(references, indent=2), encoding="utf-8")
    event = selected[0]
    evidence = "\n".join(f"- {reason}" for reason in event.get("reasons", []))
    report = (f"Thermal Intelligence: sample incident report\n\nEvent: {event['id']}\n"
              f"Location: {event.get('region', event.get('state', ''))}\n"
              f"Coordinates: {event['latitude']}, {event['longitude']}\n"
              f"Observed: {event['acqDate']}\nExport generated: {result['generatedAt']}\n"
              f"Saved source: {result['source']} (this report uses an existing snapshot)\n"
              f"Classification: {event.get('category')}\nRisk: {event.get('riskLevel')} ({event.get('riskScore')}/100)\n"
              f"Peak FRP: {event.get('frp')} MW\nDays detected: {event.get('persistenceDays')}\n\n"
              f"Evidence:\n{evidence}\n\nHuman verification required. Satellite screening does not confirm a fire.\n"
              "Model agreement with rule labels is not independently verified accuracy.\n")
    (output_dir / "sample-incident.txt").write_text(report, encoding="utf-8")
    document = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Sample incident report</title><style>body{font:16px/1.6 system-ui;margin:32px auto;padding:0 20px;max-width:850px}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
                f'<main><pre>{html.escape(report)}</pre></main></html>')
    (output_dir / "sample-incident.html").write_text(document, encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "holo-view-maker/public/data/events.json")
    parser.add_argument("--out", type=Path, default=ROOT / "output/sih-demo")
    args = parser.parse_args()
    try:
        result = prepare(args.input, args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Demo preflight failed: {exc}")
        return 1
    print(f"PASS: {result['events']} events; observations {result['observationStart']} to {result['observationEnd']}; age {result['ageDays']} days")
    print(f"Artifacts: {args.out}")
    print(result["limitation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
