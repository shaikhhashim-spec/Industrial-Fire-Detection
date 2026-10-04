"""Enrich assembled snapshot copies without ingestion or changing source feeds."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.export_3d_globe import augment_thermal_snapshot  # noqa: E402


def precompute(globe: Path, site: Path) -> int:
    count = 0
    for name in ("events.json", "global-events.json"):
        source = globe / "data" / name
        if not source.is_file():
            continue
        for folder in (site / "globe" / "data", site / "data"):
            augment_thermal_snapshot(source, folder / name)
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--globe", type=Path, default=ROOT / "holo-view-maker" / ".output" / "public")
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    print(f"Precomputed thermal change for {precompute(args.globe, args.site)} snapshot feeds; no ingestion.")
