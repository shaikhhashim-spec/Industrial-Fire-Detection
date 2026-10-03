"""Small DB-API adapter; SQL templates and identifiers are always code-owned."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading


MIGRATIONS = (
    (1, (
        "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('analyst','admin')), active INTEGER NOT NULL DEFAULT 1)",
        "CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username), expires_at DOUBLE PRECISION NOT NULL)",
        "CREATE TABLE reviews (scope TEXT NOT NULL, event_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(scope,event_id))",
        "CREATE TABLE audit (id TEXT PRIMARY KEY, scope TEXT NOT NULL, event_id TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL)",
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, scope TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL, claim_token TEXT, lease_until DOUBLE PRECISION, attempts INTEGER NOT NULL DEFAULT 0, error TEXT)",
        "CREATE TABLE rate_limits (bucket TEXT PRIMARY KEY, window_start INTEGER NOT NULL, hits INTEGER NOT NULL)",
        "CREATE INDEX sessions_expiry ON sessions(expires_at)",
        "CREATE INDEX jobs_queue ON jobs(status,created_at)",
    )),
)


def placeholders(count, postgres=False):
    return ', '.join(['%s' if postgres else '?'] * count)


class Database:
    def __init__(self, url):
        self.postgres = url.startswith(('postgres://', 'postgresql://'))
        self.lock = threading.RLock()
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            self.connection = psycopg.connect(url, row_factory=dict_row, connect_timeout=10,
                                              options='-c statement_timeout=10000 -c lock_timeout=10000')
        else:
            if '://' in url and not url.startswith('sqlite:///'):
                raise ValueError('Unsupported DATABASE_URL')
            path = url.removeprefix('sqlite:///')
            if path != ':memory:':
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(path, timeout=30, check_same_thread=False, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA journal_mode=WAL')
        self.migrate()

    def execute(self, sql, params=()):
        # Only static templates use '?' markers; values go separately to DB-API.
        if self.postgres:
            sql = sql.replace('?', placeholders(1, postgres=True))
        return self.connection.execute(sql, params)

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.postgres:
                with self.connection.transaction():
                    self.execute('SELECT pg_advisory_xact_lock(26162001)')
                    yield self
                return
            try:
                self.execute('BEGIN IMMEDIATE')
                yield self
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    def migrate(self):
        with self.transaction():
            self.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)')
            versions = {r['version'] for r in self.execute('SELECT version FROM schema_migrations').fetchall()}
            if versions - {v for v, _ in MIGRATIONS}:
                raise RuntimeError('Database schema is newer than this server')
            for version, statements in MIGRATIONS:
                if version not in versions:
                    for statement in statements:
                        self.execute(statement)
                    self.execute('INSERT INTO schema_migrations(version) VALUES (?)', (version,))

    def close(self):
        with self.lock:
            self.connection.close()
