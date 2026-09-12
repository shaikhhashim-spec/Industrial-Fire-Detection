"""Start the whole Thermal Intelligence site with one command.

    .venv\\Scripts\\python start_all.py            (Windows)
    .venv/bin/python start_all.py                 (macOS / Linux)

  * refreshes the live national FIRMS run first if it is older than 6 hours
    (skip with --no-refresh), so the dashboard and the globe open on fresh data
  * starts the 3D globe (holo-view-maker, http://localhost:8080) and the
    Streamlit dashboard (http://localhost:8501). The dashboard's
    "3D Globe" page embeds the globe, so the two are one site
  * opens the dashboard in your browser (skip with --no-browser)
  * Ctrl+C stops both
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GLOBE_DIR = ROOT / "holo-view-maker"
GLOBE_PORT, DASH_PORT = 8080, 8501
SNAPSHOT = ROOT / "data" / "processed" / "national_latest.pkl"
STALE_AFTER_S = 6 * 3600


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(port: int, timeout: float, name: str) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return True
        time.sleep(0.5)
    print(f"  ! {name} did not come up on port {port} within {timeout:.0f}s")
    return False


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":  # npm/streamlit spawn children; kill the whole tree
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-refresh", action="store_true", help="don't refresh live FIRMS data before starting")
    ap.add_argument("--no-browser", action="store_true", help="don't open the dashboard in a browser")
    args = ap.parse_args()

    if not args.no_refresh:
        age = time.time() - SNAPSHOT.stat().st_mtime if SNAPSHOT.exists() else None
        if age is None or age > STALE_AFTER_S:
            print("• Refreshing live NASA FIRMS data for India (about a minute)…")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "refresh_national_globe.py")], cwd=ROOT)
            if r.returncode != 0:
                print("  ! refresh failed, starting with the last saved data")
        else:
            print(f"• Live data is {age / 3600:.1f} h old, no refresh needed")

    procs: list[subprocess.Popen] = []
    if port_open(GLOBE_PORT):
        print(f"• 3D globe already running on http://localhost:{GLOBE_PORT}")
    else:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            print("  ! npm not found. Install Node.js to run the 3D globe.")
        else:
            print(f"• Starting 3D globe on http://localhost:{GLOBE_PORT} …")
            procs.append(subprocess.Popen([npm, "run", "dev"], cwd=GLOBE_DIR))

    if port_open(DASH_PORT):
        print(f"• Dashboard already running on http://localhost:{DASH_PORT}")
    else:
        print(f"• Starting dashboard on http://localhost:{DASH_PORT} …")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true"], cwd=ROOT,
        ))

    ok = wait_for(GLOBE_PORT, 90, "3D globe") & wait_for(DASH_PORT, 90, "dashboard")
    print(f"\n{'Ready' if ok else 'Partly up'}: open http://localhost:{DASH_PORT} "
          "(the '3D Holo Globe' page shows the globe). Ctrl+C to stop.\n")
    if ok and not args.no_browser:
        webbrowser.open(f"http://localhost:{DASH_PORT}")

    if not procs:
        return 0
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping…")
        for p in procs:
            stop(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
