"""Run prebuilt cloud assets with one public gateway and private Streamlit."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

from start_all import ROOT, free_port, gateway_health


def cloud_environment() -> tuple[int, dict[str, str]]:
    env = os.environ.copy()
    port = int(env.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    database = urlsplit(env.get("DATABASE_URL", ""))
    demo = env.get("THERMAL_DEMO_MODE", "false").lower() in {"true", "1", "yes"}
    if not demo and (database.scheme not in {"postgres", "postgresql"} or not database.hostname):
        raise ValueError("Cloud deployment requires a PostgreSQL DATABASE_URL")
    if demo and env.get("DATABASE_URL") and (database.scheme not in {"postgres", "postgresql"} or not database.hostname):
        raise ValueError("Omit DATABASE_URL for the SQLite demo")
    if not 12 <= len(env.get("THERMAL_ADMIN_PASSWORD", "")) <= 1024:
        raise ValueError("THERMAL_ADMIN_PASSWORD must contain 12-1024 characters")
    env.update(CLOUD_MODE="true", GLOBE_URL="/globe")
    env["THERMAL_DATA_DIR"] = env.get("THERMAL_DATA_DIR") or "/var/lib/thermal/data"
    env["THERMAL_OUTPUT_DIR"] = env.get("THERMAL_OUTPUT_DIR") or "/var/lib/thermal/output"
    env["THERMAL_ADMIN_USERNAME"] = env.get("THERMAL_ADMIN_USERNAME") or "admin"
    env["THERMAL_SERVER_DB"] = env.get("THERMAL_SERVER_DB") or str(Path(env["THERMAL_DATA_DIR"]) / "server.db")
    env.setdefault("GATEWAY_SITE_DIR", str(ROOT / "_site"))
    env.setdefault("GATEWAY_GLOBE_DIR", str(ROOT / "_site" / "globe"))
    env.setdefault("GATEWAY_GLOBE_DATA_DIR", str(ROOT / "_site" / "globe" / "data"))
    env["ALERT_AUTO_DISPATCH_CRITICAL"] = "false"
    env["ALERT_AUTO_ESCALATE_CALL"] = "false"
    if demo:
        env["JOBS_ENABLED"] = "false"
        env["THERMAL_SCHEDULER_ENABLED"] = "0"
    for name in ("GATEWAY_SITE_DIR", "GATEWAY_GLOBE_DIR"):
        if not (Path(env[name]) / "index.html").is_file():
            raise ValueError(f"Missing prebuilt assets: {name}; build the Docker image first")
    return port, env


def child_commands(port: int, dashboard_port: int) -> list[list[str]]:
    return [
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(dashboard_port), "--server.address", "127.0.0.1",
         "--server.baseUrlPath", "console", "--server.headless", "true",
         "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none"],
        [sys.executable, "-m", "uvicorn", "gateway.app:create_app_from_env", "--factory",
         "--host", "0.0.0.0", "--port", str(port), "--log-level", "info"],
    ]


def stop_children(children: list[subprocess.Popen]) -> None:
    # Signal both first, then share one deadline so shutdown fits Render's grace period.
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 10
    for child in reversed(children):
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def supervise(port: int, env: dict[str, str], timeout: float = 180) -> int:
    children: list[subprocess.Popen] = []
    stopping = False
    previous = {}

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, request_stop)
        dashboard_port = free_port()
        while dashboard_port == port:
            dashboard_port = free_port()
        child_env = {**env, "GATEWAY_DASH_PORT": str(dashboard_port)}
        for command in child_commands(port, dashboard_port):
            if stopping:
                return 0
            children.append(subprocess.Popen(command, cwd=ROOT, env=child_env))
        deadline = time.monotonic() + timeout
        ready = False
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("Cloud child exited; stopping service", file=sys.stderr)
                return 1
            if not ready:
                health = gateway_health(port)
                ready = bool(health and health.get("ready") is True)
                if ready:
                    print(f"Cloud gateway ready on 0.0.0.0:{port}", flush=True)
                elif time.monotonic() >= deadline:
                    print("Cloud gateway readiness timed out", file=sys.stderr)
                    return 1
            time.sleep(0.5)
        return 0
    finally:
        stop_children(children)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> int:
    try:
        port, env = cloud_environment()
        # Refuse the old local-only gateway before binding an internet-facing port.
        from gateway.app import Config
        original = os.environ.copy()
        os.environ.update(env, GATEWAY_DASH_PORT="1")
        try:
            config = Config.from_env()
        finally:
            os.environ.clear()
            os.environ.update(original)
        if not getattr(config, "cloud_mode", False):
            raise ValueError("Gateway must implement Config.cloud_mode and admin console protection")
        return supervise(port, env)
    except (ValueError, OSError) as exc:
        print(f"Cloud startup refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
