"""Explicit local worker. Only fixed refresh scripts are executable."""
import argparse
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from . import Backend

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {'national': ROOT / 'scripts' / 'refresh_national_globe.py',
           'global': ROOT / 'scripts' / 'refresh_global_globe.py'}


def run_once(backend, *, stop=None, timeout=1800, popen=subprocess.Popen):
    """Heartbeat fences completion; terminate child on lost claim or shutdown."""
    if not backend.enabled or not backend.jobs_enabled or backend.refresh_provider != 'firms':
        raise RuntimeError('Admin bootstrap, JOBS_ENABLED=true and THERMAL_REFRESH_PROVIDER=firms required')
    import os
    if not os.getenv('FIRMS_API_KEY'):
        raise RuntimeError('FIRMS_API_KEY is required for the live refresh worker')
    stop = stop or threading.Event()
    job = backend.jobs.claim()
    if not job:
        return False
    child = None
    try:
        child = popen([sys.executable, str(SCRIPTS[job['scope']])], cwd=ROOT,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        heartbeat_at = time.monotonic()
        while child.poll() is None:
            if stop.is_set() or time.monotonic() >= deadline:
                raise RuntimeError('Refresh stopped or timed out')
            if time.monotonic() >= heartbeat_at:
                if not backend.jobs.heartbeat(job):
                    raise RuntimeError('Refresh claim lost')
                heartbeat_at = time.monotonic() + backend.jobs.lease_seconds / 3
            stop.wait(0.25)
        backend.jobs.finish(job, None if child.returncode == 0 else 'Refresh provider failed')
    except BaseException:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        backend.jobs.finish(job, 'Refresh interrupted; inspect provider locally')
        raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    stop = threading.Event()
    for name in ('SIGINT', 'SIGTERM'):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    backend = Backend.from_env()
    try:
        while not stop.is_set():
            worked = run_once(backend, stop=stop)
            if args.once:
                break
            if not worked:
                stop.wait(2)
    finally:
        backend.close()


if __name__ == '__main__':
    main()
