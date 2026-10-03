"""Durable refresh queue with fencing tokens and renewable claims."""
import secrets
import time
import uuid


class JobQueue:
    def __init__(self, db, clock=time.time, lease_seconds=120, max_attempts=3):
        if lease_seconds < 3 or max_attempts < 1:
            raise ValueError('Invalid job limits')
        self.db, self.clock = db, clock
        self.lease_seconds, self.max_attempts = lease_seconds, max_attempts

    def enqueue(self, scope, actor, key):
        if scope not in {'national', 'global'} or not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError('Invalid job scope or idempotency key')
        now = self.clock()
        with self.db.transaction():
            old = self.db.execute('SELECT * FROM jobs WHERE idempotency_key=?', (key,)).fetchone()
            if old:
                if old['scope'] != scope or old['actor'] != actor:
                    raise ValueError('Idempotency key already used for another request')
                return self.public(old)
            # Bound pending work even for trusted administrators.
            count = self.db.execute("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')").fetchone()['n']
            if count >= 100:
                raise ValueError('Refresh queue is full')
            job_id = uuid.uuid4().hex
            self.db.execute('INSERT INTO jobs(id,scope,status,actor,idempotency_key,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                            (job_id, scope, 'queued', actor, key, now, now))
            return self.public(self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    @staticmethod
    def public(row):
        return {k: row[k] for k in ('id', 'scope', 'status', 'actor', 'created_at', 'updated_at', 'attempts', 'error')}

    def get(self, job_id):
        with self.db.transaction():
            row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            return self.public(row) if row else None

    def claim(self):
        now = self.clock()
        with self.db.transaction():
            self.db.execute("UPDATE jobs SET status=CASE WHEN attempts>=? THEN 'failed' ELSE 'queued' END, claim_token=NULL, lease_until=NULL, error='lease expired', updated_at=? WHERE status='running' AND lease_until<=?", (self.max_attempts, now, now))
            # Refreshes share output/history files: only one running job overall.
            if self.db.execute("SELECT id FROM jobs WHERE status='running'").fetchone():
                return None
            row = self.db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:
                return None
            token = secrets.token_hex(24)
            self.db.execute("UPDATE jobs SET status='running', claim_token=?, lease_until=?, attempts=attempts+1, error=NULL, updated_at=? WHERE id=?", (token, now + self.lease_seconds, now, row['id']))
            return dict(self.db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())

    def heartbeat(self, job):
        now = self.clock()
        with self.db.transaction():
            return self.db.execute("UPDATE jobs SET lease_until=?,updated_at=? WHERE id=? AND claim_token=? AND status='running' AND lease_until>?", (now + self.lease_seconds, now, job['id'], job['claim_token'], now)).rowcount == 1

    def finish(self, job, error=None):
        now = self.clock()
        with self.db.transaction():
            return self.db.execute("UPDATE jobs SET status=?,error=?,claim_token=NULL,lease_until=NULL,updated_at=? WHERE id=? AND claim_token=? AND status='running' AND lease_until>?", ('failed' if error else 'succeeded', error, now, job['id'], job['claim_token'], now)).rowcount == 1
