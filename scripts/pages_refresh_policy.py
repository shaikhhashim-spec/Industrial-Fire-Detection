"""Reuse recent snapshots for code pushes; scheduled/manual runs always refresh."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fresh_snapshot(path: Path, now: dt.datetime, max_age_hours: float = 6) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload["meta"]
        if meta["source"] not in {"firms_live", "local_cache", "mixed"} or not isinstance(payload["events"], list):
            return False
        timestamp = dt.datetime.fromisoformat(meta["generatedAt"].replace("Z", "+00:00"))
        age = (now - timestamp).total_seconds() / 3600
        if not 0 <= age <= max_age_hours:
            return False
        # Export time alone cannot make an older global sensor cache fresh.
        for feed in meta.get("feeds", []):
            retrieved = feed.get("retrievedAt")
            if retrieved:
                observed = dt.datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                if not 0 <= (now - observed).total_seconds() / 3600 <= max_age_hours:
                    return False
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def refresh_policy(event: str, directory: Path, now: dt.datetime) -> dict[str, bool]:
    return {
        scope: event != "push" or not fresh_snapshot(directory / filename, now)
        for scope, filename in (("global", "global-events.json"), ("national", "events.json"))
    }


if __name__ == "__main__":
    policy = refresh_policy(os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch"),
                            ROOT / "holo-view-maker" / "public" / "data", dt.datetime.now(dt.timezone.utc))
    for scope, needed in policy.items():
        print(f"{scope}_needed={str(needed).lower()}")
