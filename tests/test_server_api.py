import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from src.server import Backend, create_server, install_backend
from src.server.security import verify_password, token_hash

PASSWORD = 'test-only-password-123'


@pytest.fixture
def backend(tmp_path):
    server = Backend(str(tmp_path / 'server.db'), admin_username='admin', admin_password=PASSWORD)
    yield server
    server.close()


def login(client, username='admin'):
    response = client.post('/api/auth/login', json={'username': username, 'password': PASSWORD})
    assert response.status_code == 200
    return response.json(), {'Authorization': 'Bearer ' + response.json()['token']}


def test_fail_closed_even_with_persisted_users(tmp_path):
    path = str(tmp_path / 'server.db')
    first = Backend(path, admin_username='admin', admin_password=PASSWORD)
    first.close()
    with TestClient(create_server(Backend(path))) as client:
        assert client.post('/api/auth/login', json={'username': 'admin', 'password': PASSWORD}).status_code == 503
        assert client.get('/api/reviews/event').status_code == 503
        assert client.app.state.server.ready() is False


def test_login_hashed_sessions_roles_and_logout(backend):
    backend.create_user('analyst', PASSWORD)
    client = TestClient(create_server(backend))
    data, headers = login(client, 'analyst')
    assert data['role'] == 'analyst'
    assert client.get('/api/auth/me', headers=headers).json()['actor']['username'] == 'analyst'
    with backend.db.transaction():
        user = backend.db.execute('SELECT * FROM users WHERE username=?', ('analyst',)).fetchone()
        session = backend.db.execute('SELECT * FROM sessions').fetchone()
    assert PASSWORD not in user['password_hash']
    assert verify_password(PASSWORD, user['password_hash'])
    assert session['token_hash'] == token_hash(data['token']) and data['token'] != session['token_hash']
    assert client.post('/api/jobs', json={'scope': 'national'}, headers=headers).status_code == 403
    assert client.post('/api/auth/logout', json={}, headers=headers).status_code == 200
    assert client.get('/api/auth/me', headers=headers).status_code == 401


def test_expiry_and_user_rotation_revoke_sessions(tmp_path):
    now = [1000.0]
    backend = Backend(str(tmp_path / 'server.db'), admin_username='admin', admin_password=PASSWORD, clock=lambda: now[0], session_seconds=2)
    with TestClient(create_server(backend)) as client:
        _, headers = login(client)
        now[0] += 3
        assert client.get('/api/auth/me', headers=headers).status_code == 401
        _, headers = login(client)
        backend.create_user('admin', PASSWORD, 'admin')
        assert client.get('/api/auth/me', headers=headers).status_code == 401


def test_scope_cas_audit_restart_and_unsafe_values_are_parameters(tmp_path):
    path = str(tmp_path / 'server.db')
    backend = Backend(path, admin_username='admin', admin_password=PASSWORD)
    with TestClient(create_server(backend)) as client:
        _, headers = login(client)
        url = '/api/reviews/event-1?scope=global'
        assert client.put(url, json={'version': 0, 'review': {} }).status_code == 401
        notes = "'); DROP TABLE users; -- <script>alert(1)</script>"
        response = client.put(url, json={'version': 0, 'review': {'notes': notes, 'bookmarked': True}}, headers=headers)
        assert response.status_code == 200 and response.json()['version'] == 1
        assert client.put(url, json={'version': 0, 'review': {}}, headers=headers).status_code == 409
        assert client.get('/api/reviews/event-1?scope=india', headers=headers).json()['version'] == 0
        with backend.db.transaction():
            assert backend.db.execute('SELECT COUNT(*) AS n FROM audit').fetchone()['n'] == 1
            assert backend.db.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n'] == 1
    backend = Backend(path, admin_username='admin', admin_password=PASSWORD)
    with TestClient(create_server(backend)) as client:
        _, headers = login(client)
        assert client.get(url, headers=headers).json()['review']['notes'] == notes


def test_concurrent_review_writers_only_one_commits(tmp_path):
    path = str(tmp_path / 'server.db')
    servers = [Backend(path, admin_username='admin', admin_password=PASSWORD) for _ in range(2)]
    from src.server import Actor
    def write(server):
        try:
            return server.put_review('india', 'event', Actor('admin', 'admin'), {'version': 0, 'review': {}})['version']
        except HTTPException as exc:
            return exc.status_code
    try:
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(write, servers)) == [1, 409]
    finally:
        for server in servers:
            server.close()


def test_review_and_audit_rollback_together(backend):
    from src.server import Actor
    with backend.db.transaction():
        backend.db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(Exception):
        backend.put_review('india', 'event', Actor('admin', 'admin'), {'version': 0, 'review': {}})
    assert backend.get_review('india', 'event')['version'] == 0


def test_basic_console_role_rate_and_api_csrf(backend):
    backend.create_user('analyst', PASSWORD)
    def basic(username):
        return 'Basic ' + base64.b64encode(f'{username}:{PASSWORD}'.encode()).decode()
    assert asyncio.run(backend.authorize_admin_basic(basic('admin'), client_key='ip')).role == 'admin'
    with pytest.raises(HTTPException) as exc:
        asyncio.run(backend.authorize_admin_basic(basic('analyst'), client_key='other'))
    assert exc.value.status_code == 403
    backend.login_rate_limit = 1
    for _ in range(12):
        assert asyncio.run(backend.authorize_admin_basic(basic('admin'), client_key='rate')).role == 'admin'
    bad = 'Basic ' + base64.b64encode(b'admin:wrong-password').decode()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(backend.authorize_admin_basic(bad, client_key='rate'))
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        asyncio.run(backend.authorize_admin_basic(bad, client_key='rate'))
    assert exc.value.status_code == 429
    client = TestClient(create_server(backend))
    assert client.put('/api/reviews/event', json={'version': 0, 'review': {}}, headers={'Authorization': basic('admin')}).status_code == 401


def test_limits_include_streamed_body_and_login_attempts(backend):
    backend.body_limit = 100
    client = TestClient(create_server(backend))
    assert client.post('/api/auth/login', content=b'x' * 101, headers={'Content-Type': 'application/json'}).status_code == 413
    def chunks():
        yield b'x' * 60
        yield b'x' * 60
    assert client.post('/api/auth/login', content=chunks(), headers={'Content-Type': 'application/json'}).status_code == 413
    assert client.post('/api/auth/login', content='[]', headers={'Content-Type': 'application/json'}).status_code == 400
    assert client.post('/api/auth/login', content='{}').status_code == 415
    backend.login_rate_limit = 6
    assert client.post('/api/auth/login', json={'username': 'missing', 'password': 'incorrect'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'incorrect'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'incorrect'}).status_code == 429


def test_api_ip_rate_persists_restart(tmp_path):
    path = str(tmp_path / 'rate.db')
    backend = Backend(path, admin_username='admin', admin_password=PASSWORD, rate_limit=1, clock=lambda: 1000)
    with TestClient(create_server(backend)) as client:
        assert client.get('/api/auth/me').status_code == 401
        assert client.get('/api/auth/me').status_code == 429
    with TestClient(create_server(Backend(path, admin_username='admin', admin_password=PASSWORD, rate_limit=1, clock=lambda: 1000))) as client:
        assert client.get('/api/auth/me').status_code == 429


def test_env_uses_writable_data_directory_and_jobs_fail_closed(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('THERMAL_SERVER_DB', raising=False)
    monkeypatch.delenv('JOBS_ENABLED', raising=False)
    monkeypatch.setenv('THERMAL_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('THERMAL_ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('THERMAL_ADMIN_PASSWORD', PASSWORD)
    backend = Backend.from_env()
    try:
        assert (tmp_path / 'server.db').is_file()
        assert backend.jobs_enabled is False
    finally:
        backend.close()


@pytest.mark.parametrize('body', [
    {'version': True, 'review': {}}, {'version': -1, 'review': {}},
    {'version': 0, 'review': {'command': 'dispatch'}},
    {'version': 0, 'review': {'notes': ['wrong']}},
    {'version': 0, 'review': {'bookmarked': 'true'}},
    {'version': 0, 'review': {'status': 'verified'}},
])
def test_invalid_review_is_rejected(backend, body):
    client = TestClient(create_server(backend))
    _, headers = login(client)
    assert client.put('/api/reviews/event', json=body, headers=headers).status_code == 400
    assert client.get('/api/reviews/event?scope=national', headers=headers).status_code == 400


def test_install_routes_precede_catchall_and_alias_state(backend):
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    async def fallback(request):
        return PlainTextResponse('fallback')
    app = Starlette(routes=[Route('/{path:path}', fallback)])
    install_backend(app, backend)
    assert app.state.server is backend and app.state.backend is backend
    assert TestClient(app).get('/api/auth/me').status_code == 401
    assert backend.ready() is True


def test_jobs_default_unavailable_then_explicit_enablement(backend):
    client = TestClient(create_server(backend))
    _, headers = login(client)
    headers['Idempotency-Key'] = 'test-key'
    backend.refresh_provider = 'firms'
    response = client.post('/api/jobs', json={'scope': 'national'}, headers=headers)
    assert response.status_code == 503 and 'unavailable' in response.json()['error']
    backend.jobs_enabled = True
    response = client.post('/api/jobs', json={'scope': 'national'}, headers=headers)
    assert response.status_code == 200 and response.json()['status'] == 'queued'
    job_id = response.json()['id']
    assert client.post('/api/jobs', json={'scope': 'national'}, headers=headers).json()['id'] == job_id
    assert client.post('/api/jobs', json={'scope': 'global'}, headers=headers).status_code == 400
    assert client.get('/api/jobs/' + job_id, headers=headers).json()['status'] == 'queued'
    assert client.get('/api/jobs/missing', headers=headers).status_code == 404
    assert client.post('/api/jobs', json={'scope': 'dispatch'}, headers=headers).status_code == 400
    assert client.post('/api/jobs', json={'scope': 'national', 'command': 'anything'}, headers=headers).status_code == 400
