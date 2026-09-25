"""The one-port gateway: host routing, the proxy, the static globe, WebSockets."""
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

from gateway.app import Config, create_app, target_for


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fake_upstream() -> Starlette:
    async def index(request: Request):
        return PlainTextResponse(f"host={request.headers['host']} xfh={request.headers.get('x-forwarded-host')}")

    async def echo(request: Request):
        return PlainTextResponse((await request.body()).decode() + f"|origin={request.headers.get('origin')}")

    async def redirect(request: Request):
        origin = f"http://{request.headers['host']}"
        return Response(status_code=302, headers={"Location": f"{origin}/landed"})

    async def framed(request: Request):
        return PlainTextResponse(
            "ok", headers={"X-Frame-Options": "SAMEORIGIN", "Strict-Transport-Security": "max-age=1"}
        )

    async def cookies(request: Request):
        response = PlainTextResponse("ok")
        response.headers.append("set-cookie", "a=1; Path=/")
        response.headers.append("set-cookie", "b=2; Path=/")
        return response

    async def ws(websocket: WebSocket):
        offered = websocket.scope.get("subprotocols") or []
        await websocket.accept(subprotocol=offered[0] if offered else None)
        await websocket.send_text(f"origin={websocket.headers.get('origin')}")
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await websocket.send_bytes(message["bytes"][::-1])
            else:
                await websocket.send_text(message["text"].upper())

    return Starlette(
        routes=[
            Route("/", index),
            Route("/echo", echo, methods=["POST"]),
            Route("/redirect", redirect),
            Route("/framed", framed),
            Route("/cookies", cookies),
            WebSocketRoute("/ws", ws),
        ]
    )


@pytest.fixture(scope="module")
def upstream_port():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_fake_upstream(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    yield port
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def globe(tmp_path: Path):
    build = tmp_path / "build"
    (build / "assets").mkdir(parents=True)
    (build / "vendor").mkdir()
    (build / "data").mkdir()
    (build / "index.html").write_text("<html>globe</html>")
    (build / "assets" / "app-abc123.js").write_text("console.log(1)")
    (build / "vendor" / "worker.mjs").write_text("export {}")
    (build / "data" / "events.json").write_text('{"from":"build"}')
    (build / "data" / "only-in-build.json").write_text("{}")
    live = tmp_path / "live"
    live.mkdir()
    (live / "events.json").write_text('{"from":"live"}')
    (tmp_path / "secret.txt").write_text("do not serve")
    return build, live


def _client(upstream_port, globe, host="localhost", osiris_port=None):
    build, live = globe
    config = Config(dashboard_port=upstream_port, osiris_port=osiris_port, globe_dir=build, globe_data_dir=live)
    return TestClient(create_app(config), base_url=f"http://{host}:8085")


@pytest.mark.parametrize(
    "host, target",
    [
        ("localhost:8085", "dashboard"),
        ("127.0.0.1:8085", "dashboard"),
        ("[::1]:8085", "dashboard"),
        ("localhost", "dashboard"),
        ("globe.localhost:8085", "globe"),
        ("GLOBE.localhost:8085", "globe"),
        ("osiris.localhost:8085", "osiris"),
        ("", "dashboard"),
        ("evil.globe.localhost:8085", "dashboard"),
    ],
)
def test_target_for(host, target):
    assert target_for(host) == target


def test_dashboard_requests_reach_the_dashboard_with_the_upstream_host(upstream_port, globe):
    with _client(upstream_port, globe) as client:
        body = client.get("/").text
    assert body == f"host=127.0.0.1:{upstream_port} xfh=localhost:8085"


def test_request_bodies_and_origin_are_forwarded(upstream_port, globe):
    with _client(upstream_port, globe) as client:
        r = client.post("/echo", content="payload", headers={"origin": "http://localhost:8085"})
    assert r.text == f"payload|origin=http://127.0.0.1:{upstream_port}"


def test_redirects_point_back_at_the_gateway(upstream_port, globe):
    with _client(upstream_port, globe) as client:
        r = client.get("/redirect", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "http://localhost:8085/landed"


def test_repeated_headers_survive(upstream_port, globe):
    with _client(upstream_port, globe) as client:
        r = client.get("/cookies")
    assert r.headers.get_list("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]


def test_only_osiris_loses_its_framing_headers(upstream_port, globe):
    with _client(upstream_port, globe, osiris_port=upstream_port) as dashboard:
        assert dashboard.get("/framed").headers["x-frame-options"] == "SAMEORIGIN"
    with _client(upstream_port, globe, host="osiris.localhost", osiris_port=upstream_port) as osiris:
        headers = osiris.get("/framed").headers
    assert "x-frame-options" not in headers and "strict-transport-security" not in headers


def test_osiris_host_says_so_when_it_was_left_out(upstream_port, globe):
    with _client(upstream_port, globe, host="osiris.localhost") as client:
        r = client.get("/")
    assert r.status_code == 503 and "OSIRIS is not running" in r.text
    assert 'http-equiv="refresh"' not in r.text


def test_a_program_that_is_still_starting_gets_a_page_that_retries(globe):
    with _client(_free_port(), globe) as client:
        r = client.get("/")
    assert r.status_code == 503
    assert 'http-equiv="refresh"' in r.text and "starting" in r.text


def test_globe_serves_the_app_and_falls_back_to_it_for_routes(upstream_port, globe):
    with _client(upstream_port, globe, host="globe.localhost") as client:
        assert client.get("/").text == "<html>globe</html>"
        assert client.get("/some/route").text == "<html>globe</html>"
        assert client.get("/missing.js").status_code == 404


def test_globe_reads_live_data_first_and_the_build_second(upstream_port, globe):
    with _client(upstream_port, globe, host="globe.localhost") as client:
        assert client.get("/data/events.json").json() == {"from": "live"}
        assert client.get("/data/only-in-build.json").status_code == 200


def test_globe_caching(upstream_port, globe):
    with _client(upstream_port, globe, host="globe.localhost") as client:
        assert "immutable" in client.get("/assets/app-abc123.js").headers["cache-control"]
        assert "immutable" in client.get("/vendor/worker.mjs").headers["cache-control"]
        assert client.get("/").headers["cache-control"] == "no-cache"
        assert client.get("/data/events.json").headers["cache-control"] == "no-cache"


def test_module_workers_get_a_javascript_type(upstream_port, globe):
    with _client(upstream_port, globe, host="globe.localhost") as client:
        assert client.get("/vendor/worker.mjs").headers["content-type"].startswith("text/javascript")


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/data/../../secret.txt", "/..%2fsecret.txt"])
def test_globe_never_serves_outside_its_folders(upstream_port, globe, path):
    with _client(upstream_port, globe, host="globe.localhost") as client:
        r = client.get(path)
    assert "do not serve" not in r.text


def test_globe_is_read_only(upstream_port, globe):
    with _client(upstream_port, globe, host="globe.localhost") as client:
        assert client.post("/").status_code == 405


def test_globe_that_was_never_built_says_how_to_build_it(upstream_port, tmp_path):
    config = Config(dashboard_port=upstream_port, globe_dir=tmp_path / "nothing", globe_data_dir=tmp_path)
    with TestClient(create_app(config), base_url="http://globe.localhost:8085") as client:
        r = client.get("/")
    assert r.status_code == 503 and "npm run build" in r.text


def test_health_reports_each_program(upstream_port, globe):
    with _client(upstream_port, globe, osiris_port=_free_port()) as client:
        assert client.get("/__gateway/health").json() == {"dashboard": True, "osiris": False, "globe": True}
    with _client(upstream_port, globe) as client:
        assert client.get("/__gateway/health").json()["osiris"] is None


def test_websockets_pass_through_with_their_subprotocol(upstream_port, globe):
    with _client(upstream_port, globe) as client:
        with client.websocket_connect("/ws", subprotocols=["streamlit"]) as ws:
            assert ws.accepted_subprotocol == "streamlit"
            assert ws.receive_text() == f"origin=http://127.0.0.1:{upstream_port}"
            ws.send_text("hello")
            assert ws.receive_text() == "HELLO"
            ws.send_bytes(b"abc")
            assert ws.receive_bytes() == b"cba"


def test_websockets_to_the_globe_host_are_refused(upstream_port, globe):
    with _client(upstream_port, globe) as client:
        # A WebSocket takes its host from the URL, not from the client's base URL.
        with pytest.raises(Exception):
            with client.websocket_connect("ws://globe.localhost:8085/ws"):
                pass
