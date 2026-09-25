"""Start the whole Thermal Intelligence platform on ONE address.

    .venv\\Scripts\\python start_all.py            (Windows)
    .venv/bin/python start_all.py                 (macOS / Linux)

Then open http://localhost:8085. Everything is inside it: the dashboard, the 3D
globe and OSIRIS. There is nothing else to open or remember.

What it does, in order:

  * refreshes the live national FIRMS run if it is older than 6 hours (skip
    with --no-refresh), so every part opens on fresh data
  * builds the 3D globe if it has not been built or its source changed, and
    installs OSIRIS's dependencies the first time
  * starts the dashboard and OSIRIS on private loopback ports, then one gateway
    (gateway/app.py) on 8085 that serves all three. The private ports are picked
    free at each start, so they can never clash with anything else
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
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GLOBE_DIR = ROOT / "holo-view-maker"
GLOBE_BUILD = GLOBE_DIR / ".output" / "public"
GLOBE_STAMP = GLOBE_BUILD / ".gateway-build"
OSIRIS_DIR = ROOT / "osiris"
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
    if os.name == "nt":  # npm and streamlit spawn children; kill the whole tree
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
    """The gateway serves the globe's production build from the site root. A
    build made for GitHub Pages (a /<repo>/ base) would not load there, so the
    build is stamped and a missing stamp means it is not ours."""
    index = GLOBE_BUILD / "index.html"
    if force or not index.is_file() or not GLOBE_STAMP.is_file():
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
    env["BASE_PATH"] = "/"
    if not run([npm, "run", "build"], GLOBE_DIR, env):
        return False
    GLOBE_STAMP.write_text(json.dumps({"base": "/", "builtAt": time.time()}), encoding="utf-8")
    return True


def gateway_health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__gateway/health", timeout=2) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_until_ready(port: int, want_osiris: bool, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        health = gateway_health(port)
        if health and health["dashboard"] and health["globe"] and (health["osiris"] or not want_osiris):
            return True
        time.sleep(0.5)
    return False


def warm_up(url: str) -> None:
    """Ask once, quietly, so the first person to open a page does not wait for the
    development server to compile it."""
    try:
        urllib.request.urlopen(url, timeout=180).read(1)
    except (urllib.error.URLError, OSError):
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"the one address to serve on (default {DEFAULT_PORT})")
    ap.add_argument("--no-refresh", action="store_true", help="don't refresh live FIRMS data before starting")
    ap.add_argument("--no-browser", action="store_true", help="don't open the address in a browser")
    ap.add_argument("--no-osiris", action="store_true", help="leave OSIRIS out")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the 3D globe even if it looks up to date")
    args = ap.parse_args()
    port = args.port

    if port_open(port):
        print(f"! Port {port} is already in use. If the platform is already running, open "
              f"http://localhost:{port}; otherwise pick another port with --port.")
        return 1
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("! npm not found. Install Node.js: the 3D globe and OSIRIS need it.")
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

    use_osiris = not args.no_osiris and (OSIRIS_DIR / "package.json").is_file()
    if use_osiris and not (OSIRIS_DIR / "node_modules").is_dir():
        print("• Installing OSIRIS's dependencies (first run only) …")
        if not run([npm, "ci", "--no-audit", "--no-fund"], OSIRIS_DIR):
            print("  ! OSIRIS did not install, so it is left out this time.")
            use_osiris = False

    dash_port = free_port()
    osiris_port = free_port() if use_osiris else None

    # What the dashboard embeds. Both are on the one port, told apart by host name.
    env = os.environ.copy()
    env["GLOBE_URL"] = f"http://globe.localhost:{port}"
    if use_osiris:
        env["OSIRIS_URL"] = f"http://osiris.localhost:{port}"
    else:
        env.pop("OSIRIS_URL", None)

    procs: list[subprocess.Popen] = []
    try:
        if use_osiris:
            print("• Starting OSIRIS …")
            osiris_env = {**env, "NEXT_TELEMETRY_DISABLED": "1"}
            procs.append(subprocess.Popen(
                [npm, "run", "dev", "--", "-p", str(osiris_port), "-H", "127.0.0.1"], cwd=OSIRIS_DIR, env=osiris_env,
            ))

        print("• Starting the dashboard …")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py",
             "--server.port", str(dash_port), "--server.address", "127.0.0.1",
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            cwd=ROOT, env=env,
        ))

        print(f"• Starting the gateway on http://localhost:{port} …")
        gateway_env = {**env, "GATEWAY_DASH_PORT": str(dash_port)}
        if use_osiris:
            gateway_env["GATEWAY_OSIRIS_PORT"] = str(osiris_port)
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "gateway.app:create_app_from_env", "--factory",
             "--host", "localhost", "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env=gateway_env,
        ))

        ready = wait_until_ready(port, use_osiris, timeout=180)
        if not ready:
            print("\n! Not everything came up within 3 minutes. Whatever did is available at "
                  f"http://localhost:{port}; anything still starting reloads itself when ready.")
        else:
            print(f"\nReady: open http://localhost:{port}")
            print("  The dashboard, the 3D globe and OSIRIS are all inside it. Ctrl+C stops everything.\n")
        if use_osiris:
            threading.Thread(target=warm_up, args=(f"http://127.0.0.1:{osiris_port}/",), daemon=True).start()
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
