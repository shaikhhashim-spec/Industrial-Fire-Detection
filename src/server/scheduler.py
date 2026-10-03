"""Opt-in periodic enqueue only; does not run refreshes or dispatch alerts."""
import argparse
import os
import signal
import threading

from . import Backend


def enqueue_due(backend, scopes, period, now=None):
    if not backend.enabled or not backend.jobs_enabled or backend.refresh_provider != 'firms' or os.getenv('THERMAL_SCHEDULER_ENABLED') != '1':
        raise RuntimeError('Scheduler requires explicit enablement, admin bootstrap and firms provider')
    if period < 300:
        raise ValueError('Scheduler period must be at least 300 seconds')
    actor = os.environ['THERMAL_ADMIN_USERNAME']
    now = backend.clock() if now is None else now
    return [backend.jobs.enqueue(scope, actor, f'schedule:{scope}:{int(now // period)}') for scope in scopes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['national', 'global'], action='append', required=True)
    parser.add_argument('--period', type=int, default=3600)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    stop = threading.Event()
    for name in ('SIGINT', 'SIGTERM'):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    backend = Backend.from_env()
    try:
        while not stop.is_set():
            enqueue_due(backend, args.scope, args.period)
            if args.once:
                break
            stop.wait(min(args.period, 30))
    finally:
        backend.close()


if __name__ == '__main__':
    main()
