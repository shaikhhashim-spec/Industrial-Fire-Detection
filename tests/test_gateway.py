"""The one-port gateway: the proxied dashboard, the static globe under /globe/, WebSockets."""
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

from gateway.app import Config, create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fake_dashboard() -> Starlette:
    async def index(request: Request):
        return PlainTextResponse(f"host={request.headers['host']} xfh={request.headers.get('x-forwarded-host')}")

    async def whoami(request: Request):
        return PlainTextResponse(f"dashboard:{request.url.path}?{request.url.query}")

    async def echo(request: Request):
        return PlainTextResponse((await request.body()).decode() + f"|origin={request.headers.get('origin')}")

    async def redirect(request: Request):
        origin = f"http://{request.headers['host']}"
        return Response(status_code=302, headers={"Location": f"{origin}/landed"})

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
            Route("/cookies", cookies),
            Route("/globex", whoami),
            Route("/globe-x/{rest:path}", whoami),
            Route("/_stcore/health", whoami),
            WebSocketRoute("/ws", ws),
        ]
    )


@pytest.fixture(scope="module")
def dashboard_port():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_fake_dashboard(), host="127.0.0.1", port=port, log_level="error"))
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


def _client(dashboard_port, globe):
    build, live = globe
    config = Config(dashboard_port=dashboard_port, globe_dir=build, globe_data_dir=live)
    return TestClient(create_app(config), base_url="http://localhost:8085")


def test_requests_reach_the_dashboard_with_the_upstream_host(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        body = client.get("/").text
    assert body == f"host=127.0.0.1:{dashboard_port} xfh=localhost:8085"


def test_paths_and_queries_reach_the_dashboard_untouched(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert client.get("/_stcore/health?x=1").text == "dashboard:/_stcore/health?x=1"


def test_request_bodies_and_origin_are_forwarded(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        r = client.post("/echo", content="payload", headers={"origin": "http://localhost:8085"})
    assert r.text == f"payload|origin=http://127.0.0.1:{dashboard_port}"


def test_redirects_point_back_at_the_gateway(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        r = client.get("/redirect", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "http://localhost:8085/landed"


def test_repeated_headers_survive(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        r = client.get("/cookies")
    assert r.headers.get_list("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]


def test_a_dashboard_that_is_still_starting_gets_a_page_that_retries(globe):
    with _client(_free_port(), globe) as client:
        r = client.get("/")
    assert r.status_code == 503
    assert 'http-equiv="refresh"' in r.text and "starting" in r.text


def test_globe_serves_the_app_and_falls_back_to_it_for_routes(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert client.get("/globe/").text == "<html>globe</html>"
        assert client.get("/globe/some/route").text == "<html>globe</html>"
        assert client.get("/globe/missing.js").status_code == 404


def test_globe_without_a_trailing_slash_redirects_and_keeps_the_query(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        r = client.get("/globe?embed=1", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/globe/?embed=1"


@pytest.mark.parametrize("path", ["/globex", "/globe-x/anything"])
def test_only_the_globe_folder_is_the_globe(dashboard_port, globe, path):
    with _client(dashboard_port, globe) as client:
        assert client.get(path).text.startswith("dashboard:")


def test_globe_reads_live_data_first_and_the_build_second(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert client.get("/globe/data/events.json").json() == {"from": "live"}
        assert client.get("/globe/data/only-in-build.json").status_code == 200


def test_globe_caching(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert "immutable" in client.get("/globe/assets/app-abc123.js").headers["cache-control"]
        assert "immutable" in client.get("/globe/vendor/worker.mjs").headers["cache-control"]
        assert client.get("/globe/").headers["cache-control"] == "no-cache"
        assert client.get("/globe/data/events.json").headers["cache-control"] == "no-cache"


def test_module_workers_get_a_javascript_type(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert client.get("/globe/vendor/worker.mjs").headers["content-type"].startswith("text/javascript")


@pytest.mark.parametrize(
    "path",
    ["/globe/../secret.txt", "/globe/%2e%2e/secret.txt", "/globe/data/../../secret.txt", "/globe/..%2fsecret.txt"],
)
def test_globe_never_serves_outside_its_folders(dashboard_port, globe, path):
    with _client(dashboard_port, globe) as client:
        r = client.get(path)
    assert "do not serve" not in r.text


def test_globe_is_read_only(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert client.post("/globe/").status_code == 405


def test_globe_that_was_never_built_says_how_to_build_it(dashboard_port, tmp_path):
    config = Config(dashboard_port=dashboard_port, globe_dir=tmp_path / "nothing", globe_data_dir=tmp_path)
    with TestClient(create_app(config), base_url="http://localhost:8085") as client:
        r = client.get("/globe/")
    assert r.status_code == 503 and "npm run build" in r.text


def test_health_reports_each_part(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        assert client.get("/__gateway/health").json() == {"dashboard": True, "globe": True}
    build, live = globe
    down = Config(dashboard_port=_free_port(), globe_dir=build, globe_data_dir=live)
    with TestClient(create_app(down)) as client:
        assert client.get("/__gateway/health").json() == {"dashboard": False, "globe": True}


def test_websockets_pass_through_with_their_subprotocol(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        with client.websocket_connect("/ws", subprotocols=["streamlit"]) as ws:
            assert ws.accepted_subprotocol == "streamlit"
            assert ws.receive_text() == f"origin=http://127.0.0.1:{dashboard_port}"
            ws.send_text("hello")
            assert ws.receive_text() == "HELLO"
            ws.send_bytes(b"abc")
            assert ws.receive_bytes() == b"cba"


def test_the_globe_has_no_websocket(dashboard_port, globe):
    with _client(dashboard_port, globe) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/globe/ws"):
                pass
