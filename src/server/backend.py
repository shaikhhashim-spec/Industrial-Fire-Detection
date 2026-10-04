"""Starlette integration and bounded persistence API."""
import base64
import binascii
import json
import os
import re
import secrets
import time
import uuid

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.routing import Route

from .db import Database
from .jobs import JobQueue
from .security import Actor, hash_password, token_hash, verify_password
from src.review_schema import ASSESSMENT_FIELDS, validate_assessment


def default_database_url():
    from pathlib import Path
    return 'sqlite:///' + str(Path(os.getenv('THERMAL_DATA_DIR', 'data')) / 'server.db')


class Backend:
    def __init__(self, database_url='sqlite:///data/server.db', *, admin_username=None,
                 admin_password=None, refresh_provider=None, jobs_enabled=False, session_seconds=28800,
                 body_limit=65536, rate_limit=120, login_rate_limit=10, clock=time.time):
        if body_limit < 1 or session_seconds < 1 or min(rate_limit, login_rate_limit) < 1:
            raise ValueError('Server limits must be positive')
        if refresh_provider not in {None, 'firms'}:
            raise ValueError('Only the firms refresh provider is supported')
        self.clock, self.session_seconds = clock, session_seconds
        self.body_limit, self.rate_limit, self.login_rate_limit = body_limit, rate_limit, login_rate_limit
        self.refresh_provider = refresh_provider
        self.jobs_enabled = jobs_enabled
        self.enabled = bool(admin_username and admin_password)
        self.db = Database(database_url)
        self.jobs = JobQueue(self.db, clock)
        self._dummy_hash = hash_password(secrets.token_urlsafe(24))
        if self.enabled:
            try:
                self.create_user(admin_username, admin_password, 'admin', only_if_absent=True)
                with self.db.transaction():
                    row = self.db.execute('SELECT role,active FROM users WHERE username=?', (admin_username,)).fetchone()
                    if row['role'] != 'admin' or not row['active']:
                        raise ValueError('Bootstrap username must be an active administrator')
            except BaseException:
                self.close()
                raise

    @classmethod
    def from_env(cls):
        return cls(os.getenv('DATABASE_URL') or ('sqlite:///' + os.environ['THERMAL_SERVER_DB'] if os.getenv('THERMAL_SERVER_DB') else default_database_url()),
                   admin_username=os.getenv('THERMAL_ADMIN_USERNAME'),
                   admin_password=os.getenv('THERMAL_ADMIN_PASSWORD'),
                   refresh_provider=os.getenv('THERMAL_REFRESH_PROVIDER') or None,
                   jobs_enabled=os.getenv('JOBS_ENABLED', '').lower() in {'true', '1'},
                   session_seconds=int(os.getenv('THERMAL_SESSION_SECONDS', '28800')),
                   body_limit=int(os.getenv('THERMAL_BODY_LIMIT', '65536')),
                   rate_limit=int(os.getenv('THERMAL_RATE_LIMIT', '120')),
                   login_rate_limit=int(os.getenv('THERMAL_LOGIN_RATE_LIMIT', '10')))

    def close(self):
        self.db.close()

    def ready(self):
        with self.db.transaction():
            self.db.execute('SELECT version FROM schema_migrations').fetchall()
        return self.enabled

    def create_user(self, username, password, role='analyst', *, only_if_absent=False):
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,80}', username) or role not in {'analyst', 'admin'}:
            raise ValueError('Invalid username or role')
        encoded = hash_password(password)
        with self.db.transaction():
            old = self.db.execute('SELECT username FROM users WHERE username=?', (username,)).fetchone()
            if old:
                if only_if_absent:
                    return
                self.db.execute('UPDATE users SET password_hash=?,role=?,active=1 WHERE username=?', (encoded, role, username))
                self.db.execute('DELETE FROM sessions WHERE username=?', (username,))
            else:
                self.db.execute('INSERT INTO users(username,password_hash,role) VALUES (?,?,?)', (username, encoded, role))

    def _enabled(self):
        if not self.enabled:
            raise HTTPException(503, 'Secured backend is disabled')

    def _rate(self, bucket, limit, consume=True):
        now = int(self.clock())
        window = now // 60
        with self.db.transaction():
            self.db.execute('DELETE FROM rate_limits WHERE window_start<?', (window - 1,))
            row = self.db.execute('SELECT * FROM rate_limits WHERE bucket=?', (bucket,)).fetchone()
            hits = row['hits'] if row and row['window_start'] == window else 0
            if consume:
                hits += 1
                self.db.execute('INSERT INTO rate_limits(bucket,window_start,hits) VALUES (?,?,?) ON CONFLICT(bucket) DO UPDATE SET window_start=excluded.window_start,hits=excluded.hits', (bucket, window, hits))
        if hits > limit or (not consume and hits >= limit):
            raise HTTPException(429, 'Rate limit exceeded', headers={'Retry-After': str(60 - now % 60)})

    def _credentials(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 80 or len(password) > 1024:
            raise HTTPException(401, 'Invalid credentials')
        with self.db.transaction():
            row = self.db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        valid = verify_password(password, row['password_hash'] if row else self._dummy_hash)
        if not valid or not row or not row['active']:
            raise HTTPException(401, 'Invalid credentials')
        return Actor(row['username'], row['role'])

    async def authenticate(self, request):
        """Works with HTTP Request or WebSocket; ignores proxy-supplied IP headers."""
        self._enabled()
        host = request.client.host if request.client else 'unknown'
        header = request.headers.get('authorization', '')
        if len(header) > 4096:
            raise HTTPException(401, 'Invalid authorization')
        scheme, _, value = header.partition(' ')
        if scheme.lower() == 'basic':
            return await run_in_threadpool(self._basic_credentials, header, host)
        if scheme.lower() == 'bearer' and value and len(value) <= 256:
            return await run_in_threadpool(self._session_actor, value)
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Basic realm="Thermal console"'})

    async def authenticate_admin_basic(self, header, client_key='console'):
        """Header-only console gate; caller handles HTTP/WS rejection responses."""
        self._enabled()
        actor = await run_in_threadpool(self._basic_credentials, header, client_key)
        return self.require_role(actor, 'admin')

    def _basic_credentials(self, header, client_key):
        self._rate('basic:' + client_key, self.login_rate_limit, consume=False)
        try:
            return self._decode_basic(header)
        except HTTPException as exc:
            if exc.status_code == 401 and header:
                self._rate('basic:' + client_key, self.login_rate_limit)
            raise

    def _decode_basic(self, header):
        if not isinstance(header, str) or len(header) > 4096:
            raise HTTPException(401, 'Invalid credentials')
        scheme, _, value = header.partition(' ')
        if scheme.lower() != 'basic':
            raise HTTPException(401, 'Admin Basic authentication required',
                                headers={'WWW-Authenticate': 'Basic realm="Thermal console"'})
        try:
            username, password = base64.b64decode(value, validate=True).decode('utf-8').split(':', 1)
        except (ValueError, UnicodeError, binascii.Error):
            raise HTTPException(401, 'Invalid credentials') from None
        return self._credentials(username, password)

    async def authorize_admin_basic(self, header, client_key='console'):
        return await self.authenticate_admin_basic(header, client_key)

    def _session_actor(self, token):
        with self.db.transaction():
            row = self.db.execute('SELECT u.username,u.role,u.active,s.expires_at FROM sessions s JOIN users u ON s.username=u.username WHERE s.token_hash=?', (token_hash(token),)).fetchone()
        if not row or not row['active'] or row['expires_at'] <= self.clock():
            raise HTTPException(401, 'Invalid or expired session')
        return Actor(row['username'], row['role'], row['expires_at'])

    @staticmethod
    def require_role(actor, role):
        if actor is None or role not in {'analyst', 'admin'} or actor.role not in ({'admin'} if role == 'admin' else {'analyst', 'admin'}):
            raise HTTPException(403, 'Insufficient permission')
        return actor

    async def _body(self, request):
        length = request.headers.get('content-length')
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                raise HTTPException(400, 'Invalid content length') from None
            if size < 0:
                raise HTTPException(400, 'Invalid content length')
            if size > self.body_limit:
                raise HTTPException(413, 'Request body too large')
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > self.body_limit:
                raise HTTPException(413, 'Request body too large')
            body.extend(chunk)
        if request.method in {'POST', 'PUT'}:
            if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                raise HTTPException(415, 'JSON required')
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(400, 'Invalid JSON') from None
            if not isinstance(data, dict):
                raise HTTPException(400, 'JSON object required')
            return data
        return {}

    def _review_key(self, request):
        scope = request.query_params.get('scope', 'india')
        event = request.path_params['event_id']
        if scope not in {'india', 'global'} or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', event):
            raise HTTPException(400, 'Invalid review scope or event ID')
        return scope, event

    def get_review(self, scope, event):
        with self.db.transaction():
            row = self.db.execute('SELECT * FROM reviews WHERE scope=? AND event_id=?', (scope, event)).fetchone()
        if not row:
            return {'scope': scope, 'event_id': event, 'version': 0, 'review': None}
        return {'scope': scope, 'event_id': event, 'version': row['version'], 'review': json.loads(row['payload']), 'actor': row['actor'], 'updated_at': row['updated_at']}

    def put_review(self, scope, event, actor, data):
        version = data.get('version')
        review = data.get('review')
        if set(data) != {'version', 'review'} or type(version) is not int or version < 0 or not isinstance(review, dict):
            raise HTTPException(400, 'Expected version and review object')
        if set(review) - ({'notes', 'bookmarked', 'status'} | ASSESSMENT_FIELDS) or not isinstance(review.get('notes', ''), str) or len(review.get('notes', '')) > 16000 or type(review.get('bookmarked', False)) is not bool or review.get('status', 'unreviewed') not in {'unreviewed', 'investigating', 'reviewed'}:
            raise HTTPException(400, 'Invalid review fields')
        try:
            validate_assessment(review)
        except (ValueError, TypeError):
            raise HTTPException(400, 'Invalid assessment fields') from None
        payload = json.dumps(review, ensure_ascii=True, allow_nan=False)
        now = self.clock()
        with self.db.transaction():
            row = self.db.execute('SELECT version FROM reviews WHERE scope=? AND event_id=?', (scope, event)).fetchone()
            current = row['version'] if row else 0
            if current != version:
                raise HTTPException(409, 'Review version conflict')
            self.db.execute('INSERT INTO reviews(scope,event_id,version,payload,actor,updated_at) VALUES (?,?,?,?,?,?) ON CONFLICT(scope,event_id) DO UPDATE SET version=excluded.version,payload=excluded.payload,actor=excluded.actor,updated_at=excluded.updated_at', (scope, event, version + 1, payload, actor.username, now))
            self.db.execute('INSERT INTO audit(id,scope,event_id,version,actor,payload,created_at) VALUES (?,?,?,?,?,?,?)', (uuid.uuid4().hex, scope, event, version + 1, actor.username, payload, now))
        return {'scope': scope, 'event_id': event, 'version': version + 1, 'review': review, 'actor': actor.username, 'updated_at': now}

    def _login(self, data):
        if set(data) != {'username', 'password'}:
            raise HTTPException(400, 'Username and password required')
        actor = self._credentials(data['username'], data['password'])
        token = secrets.token_urlsafe(32)
        expires = self.clock() + self.session_seconds
        with self.db.transaction():
            self.db.execute('DELETE FROM sessions WHERE expires_at<=?', (self.clock(),))
            count = self.db.execute('SELECT COUNT(*) AS n FROM sessions WHERE username=?', (actor.username,)).fetchone()['n']
            if count >= 20:
                raise HTTPException(429, 'Too many active sessions; logout existing sessions')
            self.db.execute('INSERT INTO sessions(token_hash,username,expires_at) VALUES (?,?,?)', (token_hash(token), actor.username, expires))
        return {'token': token, 'actor': Actor(actor.username, actor.role, expires).public(), 'role': actor.role, 'expires_at': expires}

    def get_routes(self, prefix='/api'):
        prefix = prefix.rstrip('/')
        def endpoint(kind):
            async def handle(request):
                try:
                    self._enabled()
                    host = request.client.host if request.client else 'unknown'
                    await run_in_threadpool(self._rate, 'api:' + host, self.rate_limit)
                    if kind == 'login':
                        await run_in_threadpool(self._rate, 'login:' + host, self.login_rate_limit)
                        data = await self._body(request)
                        result = await run_in_threadpool(self._login, data)
                    else:
                        actor = await self.authenticate(request)
                        self.require_role(actor, 'admin' if kind == 'jobs' else 'analyst')
                        # Browser Basic credentials are ambient. Mutations require
                        # explicit opaque tokens, preventing Basic-auth CSRF.
                        if request.method in {'PUT', 'POST'} and not request.headers.get('authorization', '').lower().startswith('bearer '):
                            raise HTTPException(401, 'Bearer session required for mutations')
                        data = await self._body(request)
                        if kind == 'me':
                            result = {'actor': actor.public()}
                        elif kind == 'logout':
                            token = request.headers['authorization'].partition(' ')[2]
                            await run_in_threadpool(self._logout, token)
                            result = {'logged_out': True}
                        elif kind == 'review':
                            scope, event = self._review_key(request)
                            result = await run_in_threadpool(self.put_review, scope, event, actor, data) if request.method == 'PUT' else await run_in_threadpool(self.get_review, scope, event)
                        elif request.method == 'POST':
                            if not self.jobs_enabled or self.refresh_provider != 'firms':
                                raise HTTPException(503, 'Refresh execution unavailable; an explicit local worker must be configured')
                            if set(data) != {'scope'}:
                                raise HTTPException(400, 'Only scope is accepted')
                            key = request.headers.get('idempotency-key')
                            if not key:
                                raise HTTPException(400, 'Idempotency-Key required')
                            result = await run_in_threadpool(self.jobs.enqueue, data['scope'], actor.username, key)
                        else:
                            result = await run_in_threadpool(self.jobs.get, request.path_params['job_id'])
                            if result is None:
                                raise HTTPException(404, 'Job not found')
                    return JSONResponse(result, headers={'Cache-Control': 'no-store'})
                except HTTPException as exc:
                    return JSONResponse({'error': exc.detail}, status_code=exc.status_code, headers={'Cache-Control': 'no-store', **(exc.headers or {})})
                except (ValueError, TypeError):
                    return JSONResponse({'error': 'Invalid request'}, status_code=400, headers={'Cache-Control': 'no-store'})
            return handle
        return [Route(prefix + '/auth/login', endpoint('login'), methods=['POST']),
                Route(prefix + '/auth/me', endpoint('me'), methods=['GET']),
                Route(prefix + '/auth/logout', endpoint('logout'), methods=['POST']),
                Route(prefix + '/reviews/{event_id}', endpoint('review'), methods=['GET', 'PUT']),
                Route(prefix + '/jobs', endpoint('jobs'), methods=['POST']),
                Route(prefix + '/jobs/{job_id}', endpoint('jobs'), methods=['GET'])]

    def _logout(self, token):
        with self.db.transaction():
            self.db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(token),))


def install_backend(app, backend=None, prefix='/api'):
    """Install before startup; caller owns close() in its existing lifespan."""
    backend = backend or Backend.from_env()
    app.state.backend = backend
    app.state.server = backend
    app.router.routes[0:0] = backend.get_routes(prefix)
    return backend


def create_server(backend=None):
    from contextlib import asynccontextmanager
    backend = backend or Backend.from_env()
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            backend.close()
    app = Starlette(routes=backend.get_routes(), lifespan=lifespan)
    app.state.backend = backend
    app.state.server = backend
    return app
