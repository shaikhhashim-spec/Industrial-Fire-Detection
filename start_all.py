"""Start the whole Thermal Intelligence platform on ONE address.

    .venv\\Scripts\\python start_all.py            (Windows)
    .venv/bin/python start_all.py                 (macOS / Linux)

Then open http://localhost:8085. The dashboard and the 3D globe are both inside
it. There is nothing else to open or remember.

What it does, in order:

  * refreshes the live national FIRMS run if it is older than 6 hours (skip
    with --no-refresh), so everything opens on fresh data
  * builds the 3D globe if it has not been built or its source changed
  * starts the dashboard on a private loopback port, then one gateway
    (gateway/app.py) on 8085 that serves the dashboard and the globe together.
    The private port is picked free at each start, so it can never clash with
    anything else
  * opens the address in your browser (skip with --no-browser); Ctrl+C stops it all
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GLOBE_DIR = ROOT / "holo-view-maker"
GLOBE_BUILD = GLOBE_DIR / ".output" / "public"
GLOBE_STAMP = GLOBE_BUILD / ".gateway-build"
GLOBE_BASE = "/globe/"  # where the gateway serves the globe (gateway/app.py: GLOBE_PATH)
SNAPSHOT = ROOT / "data" / "processed" / "national_latest.pkl"
STALE_AFTER_S = 6 * 3600
DEFAULT_PORT = 8085


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":  # streamlit spawns children; kill the whole tree
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
    return subprocess.run(cmd, cwd=cwd, env=env).returncode == 0


def globe_needs_build(force: bool) -> bool:
    """The gateway serves the globe's production build under /globe/. A build made
    for another base (GitHub Pages, or the site root) would not load there, so a
    build is stamped with its base, and anything unstamped or stamped otherwise
    is not ours."""
    if force or not (GLOBE_BUILD / "index.html").is_file() or not GLOBE_STAMP.is_file():
        return True
    try:
        if json.loads(GLOBE_STAMP.read_text(encoding="utf-8")).get("base") != GLOBE_BASE:
            return True
    except (OSError, ValueError):
        return True
    watched = [GLOBE_DIR / "package-lock.json", GLOBE_DIR / "vite.config.ts"]
    watched += [p for p in (GLOBE_DIR / "src").rglob("*") if p.is_file()]
    return max(p.stat().st_mtime for p in watched) > GLOBE_STAMP.stat().st_mtime


def build_globe(npm: str) -> bool:
    if not (GLOBE_DIR / "node_modules").is_dir():
        print("• Installing the 3D globe's dependencies (first run only) …")
        if not run([npm, "ci"], GLOBE_DIR):
            return False
    print("• Building the 3D globe …")
    env = {k: v for k, v in os.environ.items() if k not in {"GITHUB_ACTIONS", "GITHUB_REPOSITORY"}}
    env["BASE_PATH"] = GLOBE_BASE
    if not run([npm, "run", "build"], GLOBE_DIR, env):
        return False
    GLOBE_STAMP.write_text(json.dumps({"base": GLOBE_BASE, "builtAt": time.time()}), encoding="utf-8")
    return True


def gateway_health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__gateway/health", timeout=2) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_until_ready(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        health = gateway_health(port)
        if health and health["dashboard"] and health["globe"]:
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"the one address to serve on (default {DEFAULT_PORT})")
    ap.add_argument("--no-refresh", action="store_true", help="don't refresh live FIRMS data before starting")
    ap.add_argument("--no-browser", action="store_true", help="don't open the address in a browser")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the 3D globe even if it looks up to date")
    args = ap.parse_args()
    port = args.port

    if port_open(port):
        print(f"! Port {port} is already in use. If the platform is already running, open "
              f"http://localhost:{port}; otherwise pick another port with --port.")
        return 1
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("! npm not found. Install Node.js: the 3D globe needs it.")
        return 1

    if not args.no_refresh:
        age = time.time() - SNAPSHOT.stat().st_mtime if SNAPSHOT.exists() else None
        if age is None or age > STALE_AFTER_S:
            print("• Refreshing live NASA FIRMS data for India (about a minute) …")
            if not run([sys.executable, str(ROOT / "scripts" / "refresh_national_globe.py")], ROOT):
                print("  ! refresh failed, starting with the last saved data")
        else:
            print(f"• Live data is {age / 3600:.1f} h old, no refresh needed")

    if globe_needs_build(args.rebuild) and not build_globe(npm):
        print("! The 3D globe did not build, so it would be missing. Fix the error above and run again.")
        return 1

    dash_port = free_port()
    # What the dashboard embeds: the globe, on the same address it is opened from.
    env = os.environ.copy()
    env["GLOBE_URL"] = f"http://localhost:{port}{GLOBE_BASE.rstrip('/')}"

    procs: list[subprocess.Popen] = []
    try:
        print("• Starting the dashboard …")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py",
             "--server.port", str(dash_port), "--server.address", "127.0.0.1",
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            cwd=ROOT, env=env,
        ))

        print(f"• Starting the gateway on http://localhost:{port} …")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "gateway.app:create_app_from_env", "--factory",
             "--host", "localhost", "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env={**env, "GATEWAY_DASH_PORT": str(dash_port)},
        ))

        ready = wait_until_ready(port, timeout=180)
        if not ready:
            print("\n! Not everything came up within 3 minutes. Whatever did is available at "
                  f"http://localhost:{port}; anything still starting reloads itself when ready.")
        else:
            print(f"\nReady: open http://localhost:{port}")
            print("  The dashboard and the 3D globe are both inside it. Ctrl+C stops everything.\n")
        if ready and not args.no_browser:
            webbrowser.open(f"http://localhost:{port}")

        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("\n! One of the parts stopped, so everything is being stopped.")
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping …")
        for p in procs:
            stop(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
