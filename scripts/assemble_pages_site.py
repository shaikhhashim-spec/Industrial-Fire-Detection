"""Assemble the GitHub Pages site.

The public site is the static Overview page (site/) at the root and the 3D globe's
production build under /globe/, the same shape the local gateway serves
(gateway/app.py). The globe must have been built with BASE_PATH=/<repo>/globe/.

Standard library only, so the deploy can run it before any Python is set up.

Usage:  python scripts/assemble_pages_site.py --out _site
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assemble(site_dir: Path, globe_dir: Path, out_dir: Path) -> Path:
    for needed in (site_dir / "index.html", globe_dir / "index.html"):
        if not needed.is_file():
            raise FileNotFoundError(f"{needed} is missing: build the globe first, and run from the repository")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(site_dir, out_dir, ignore=shutil.ignore_patterns("*.test.mjs"))
    shutil.copytree(globe_dir, out_dir / "globe", ignore=shutil.ignore_patterns(".gateway-build"))
    (out_dir / ".nojekyll").touch()  # Pages must serve files that start with an underscore as they are
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=ROOT / "site")
    ap.add_argument("--globe", type=Path, default=ROOT / "holo-view-maker" / ".output" / "public")
    ap.add_argument("--out", type=Path, default=ROOT / "_site")
    args = ap.parse_args()
    try:
        out = assemble(args.site, args.globe, args.out)
    except FileNotFoundError as exc:
        print(f"! {exc}")
        return 1
    print(f"assembled {out}: Overview at the root, 3D globe under globe/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
