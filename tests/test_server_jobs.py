from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from src.server.db import Database, placeholders
from src.server.jobs import JobQueue


def test_exclusive_claims_across_connections_and_scope_serialization(tmp_path):
    path = str(tmp_path / 'jobs.db')
    databases = [Database(path) for _ in range(4)]
    queues = [JobQueue(db) for db in databases]
    try:
        queues[0].enqueue('national', 'admin', 'n')
        queues[0].enqueue('global', 'admin', 'g')
        with ThreadPoolExecutor(4) as pool:
            claims = list(pool.map(lambda q: q.claim(), queues))
        assert len([c for c in claims if c]) == 1
        claim = next(c for c in claims if c)
        assert queues[0].finish(claim)
        assert queues[1].claim()['id'] != claim['id']
    finally:
        for db in databases:
            db.close()


def test_lease_recovery_fences_old_owner_and_stops_retries(tmp_path):
    now = [1000]
    db = Database(str(tmp_path / 'jobs.db'))
    q = JobQueue(db, clock=lambda: now[0], lease_seconds=3, max_attempts=2)
    try:
        job = q.enqueue('national', 'admin', 'key')
        old = q.claim()
        now[0] += 2
        assert q.heartbeat(old)
        now[0] += 4
        new = q.claim()
        assert new['id'] == old['id'] and new['claim_token'] != old['claim_token']
        assert not q.finish(old) and not q.heartbeat(old)
        now[0] += 4
        assert q.claim() is None
        assert q.get(job['id'])['status'] == 'failed'
    finally:
        db.close()


def test_queue_bounded_and_idempotent(tmp_path):
    db = Database(str(tmp_path / 'jobs.db'))
    q = JobQueue(db)
    try:
        first = q.enqueue('national', 'admin', 'first')
        assert q.enqueue('national', 'admin', 'first')['id'] == first['id']
        with pytest.raises(ValueError):
            q.enqueue('global', 'admin', 'first')
        for n in range(99):
            q.enqueue('global', 'admin', str(n))
        with pytest.raises(ValueError, match='full'):
            q.enqueue('national', 'admin', 'overflow')
    finally:
        db.close()


def test_migrations_repeat_and_parameter_helper(tmp_path):
    path = str(tmp_path / 'db.sqlite')
    db = Database(path)
    db.migrate()
    with db.transaction():
        assert len(db.execute('SELECT * FROM schema_migrations').fetchall()) == 1
    db.close()
    assert placeholders(2) == '?, ?'
    assert placeholders(2, True) == '%s, %s'


def test_scheduler_explicit_opt_in_and_period_idempotency(tmp_path, monkeypatch):
    from src.server import Backend
    from src.server.scheduler import enqueue_due
    backend = Backend(str(tmp_path / 'db'), admin_username='admin', admin_password='test-password-123', refresh_provider='firms', jobs_enabled=True)
    try:
        monkeypatch.setenv('THERMAL_ADMIN_USERNAME', 'admin')
        monkeypatch.delenv('THERMAL_SCHEDULER_ENABLED', raising=False)
        with pytest.raises(RuntimeError):
            enqueue_due(backend, ['national'], 300, now=1000)
        monkeypatch.setenv('THERMAL_SCHEDULER_ENABLED', '1')
        first = enqueue_due(backend, ['national'], 300, now=1000)
        assert enqueue_due(backend, ['national'], 300, now=1001) == first
        assert enqueue_due(backend, ['national'], 300, now=1300)[0]['id'] != first[0]['id']
        with pytest.raises(ValueError):
            enqueue_due(backend, ['national'], 10)
    finally:
        backend.close()


def test_worker_uses_fixed_scripts_without_real_providers(tmp_path, monkeypatch):
    from src.server import Backend
    from src.server.worker import run_once, SCRIPTS
    monkeypatch.setenv('FIRMS_API_KEY', 'dummy-test-only-never-sent')
    backend = Backend(str(tmp_path / 'db'), admin_username='admin', admin_password='test-password-123', refresh_provider='firms', jobs_enabled=True)
    calls = []
    class Child:
        returncode = 0
        def poll(self):
            return 0
    def fake_popen(command, **kwargs):
        calls.append(command)
        return Child()
    try:
        job = backend.jobs.enqueue('global', 'admin', 'g')
        assert run_once(backend, popen=fake_popen)
        assert calls[0][1] == str(SCRIPTS['global'])
        assert backend.jobs.get(job['id'])['status'] == 'succeeded'
        assert not run_once(backend, popen=fake_popen)
    finally:
        backend.close()


def test_worker_shutdown_terminates_child(tmp_path, monkeypatch):
    from src.server import Backend
    from src.server.worker import run_once
    monkeypatch.setenv('FIRMS_API_KEY', 'dummy-test-only-never-sent')
    backend = Backend(str(tmp_path / 'db'), admin_username='admin', admin_password='test-password-123', refresh_provider='firms', jobs_enabled=True)
    stop = threading.Event()
    stop.set()
    class Child:
        terminated = False
        def poll(self):
            return None
        def terminate(self):
            self.terminated = True
        def wait(self, timeout=None):
            return 0
    child = Child()
    try:
        job = backend.jobs.enqueue('national', 'admin', 'n')
        with pytest.raises(RuntimeError):
            run_once(backend, stop=stop, popen=lambda *a, **k: child)
        assert child.terminated
        assert backend.jobs.get(job['id'])['status'] == 'failed'
    finally:
        backend.close()
