"""Cloud public routes cannot bypass the secured operational console."""
import base64
from dataclasses import replace

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gateway.app import Config, create_app


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("THERMAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("THERMAL_ADMIN_PASSWORD", "test-password-only-123")
    monkeypatch.setenv("THERMAL_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    site = tmp_path / "site"
    site.mkdir()
    for name in ("index.html", "investigations.html", "nav.mjs", "secret.py", "hidden.test.mjs"):
        (site / name).write_text(name)
    globe = tmp_path / "globe"
    globe.mkdir()
    (globe / "index.html").write_text("globe")
    app = create_app(Config(dashboard_port=1, globe_dir=globe, site_dir=site, cloud_mode=True))
    with TestClient(app) as client:
        yield client, app


def test_public_routes_and_no_source_leak(cloud):
    client, _ = cloud
    assert client.get("/").text == "index.html"
    assert client.get("/investigations.html").text == "investigations.html"
    assert client.get("/nav.mjs").status_code == 200
    for path in ("/secret.py", "/hidden.test.mjs", "/.env", "/_stcore/health", "/api/missing"):
        assert client.get(path).status_code == 404
    assert client.post("/investigations.html").status_code == 405
    capabilities = client.get("/api/capabilities")
    assert capabilities.json() == {"reviews": True, "demo": False, "jobs": False}
    assert "www-authenticate" not in capabilities.headers


def test_console_requires_admin_and_api_requires_authentication(cloud):
    client, app = cloud
    assert client.get("/console/").status_code == 401
    app.state.server.create_user("analyst", "analyst-password-123", "analyst")
    assert client.get("/console/", auth=("analyst", "analyst-password-123")).status_code == 403
    assert client.get("/api/reviews/test?scope=india").status_code == 401
    assert client.put("/api/reviews/test?scope=india", json={}).status_code == 401
    assert client.post("/api/jobs", json={"scope": "global"}).status_code == 401


def test_cloud_readiness_is_not_false_positive(cloud):
    client, _ = cloud
    response = client.get("/__gateway/health")
    assert response.status_code == 503
    assert response.json() == {"dashboard": False, "globe": True, "site": True, "database": True, "ready": False}


def test_console_and_non_console_websockets_reject_anonymous(cloud):
    client, _ = cloud
    for path in ("/console/_stcore/stream", "/_stcore/stream"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path):
                pass


def test_admin_console_reaches_private_dashboard_only_after_auth(cloud):
    client, _ = cloud
    encoded = base64.b64encode(b"admin:test-password-only-123").decode()
    response = client.get("/console/", headers={"Authorization": "Basic " + encoded})
    assert response.status_code == 503
    assert "starting" in response.text


@pytest.mark.parametrize("origin", ["https://untrusted.example", "https://testserver"])
def test_cross_origin_console_requests_rejected_even_with_credentials(cloud, origin):
    client, _ = cloud
    response = client.post("/console/upload", auth=("admin", "test-password-only-123"),
                           headers={"Origin": origin})
    assert response.status_code == 403


def test_declared_render_https_origin_works_behind_http_proxy(cloud):
    client, app = cloud
    app.state.config = replace(app.state.config, public_origin="https://testserver")
    response = client.get("/console/", auth=("admin", "test-password-only-123"),
                          headers={"Origin": "https://testserver"})
    assert response.status_code == 503  # Authorized; private dashboard is intentionally down.
    assert client.post("/console/upload", headers={"Origin": "http://testserver"}).status_code == 403
