"""Opt-in live driver parity check against a dedicated test database only."""
import os
import uuid

import pytest

from src.server import Actor, Backend


@pytest.mark.skipif(not os.getenv('THERMAL_TEST_DATABASE_URL'), reason='Dedicated PostgreSQL test URL not configured')
def test_postgres_review_audit_and_queue_restart():
    pytest.importorskip('psycopg')
    url = os.environ['THERMAL_TEST_DATABASE_URL']
    assert url.startswith(('postgresql://', 'postgres://'))
    event = uuid.uuid4().hex
    username = 'test-' + uuid.uuid4().hex[:16]
    first = Backend(url, admin_username=username, admin_password='test-password-only-123')
    job_id = None
    try:
        assert first.ready()
        actor = Actor(username, 'admin')
        assert first.put_review('global', event, actor, {'version': 0, 'review': {'notes': "' ? %s"}})['version'] == 1
        job_id = first.jobs.enqueue('global', username, event)['id']
        second = Backend(url, admin_username=username, admin_password='test-password-only-123')
        try:
            assert second.get_review('global', event)['review']['notes'] == "' ? %s"
            assert second.jobs.get(job_id)['status'] == 'queued'
            with second.db.transaction():
                assert second.db.execute('SELECT COUNT(*) AS n FROM audit WHERE event_id=?', (event,)).fetchone()['n'] == 1
        finally:
            second.close()
    finally:
        with first.db.transaction():
            first.db.execute('DELETE FROM audit WHERE event_id=?', (event,))
            first.db.execute('DELETE FROM reviews WHERE event_id=?', (event,))
            if job_id:
                first.db.execute('DELETE FROM jobs WHERE id=?', (job_id,))
            first.db.execute('DELETE FROM users WHERE username=?', (username,))
        first.close()
