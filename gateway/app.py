"""One address for the whole platform.

The dashboard (Streamlit), the 3D globe and OSIRIS (Next.js) are separate
programs. This gateway puts all of them behind one port, so there is a single
address to open (http://localhost:8085) and nothing else to start or remember.

Routing is by host name on that one port. Browsers resolve every *.localhost
name to this machine with no setup, so each program gets its own root and none
of them has to be modified to live under a path prefix:

    localhost:8085          the dashboard (proxied to Streamlit)
    globe.localhost:8085    the 3D globe (its production build, served here)
    osiris.localhost:8085   OSIRIS (proxied to its dev server)

The dashboard embeds the other two, so a visitor only ever types the first.
The upstream servers listen on private loopback ports picked by start_all.py.
The gateway itself is meant to be bound to localhost only.
"""
from __future__ import annotations

import asyncio
import mimetypes
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import websockets
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

# Windows can map .mjs to text/plain, which browsers refuse for module workers,
# and the globe's map worker is exactly that.
mimetypes.add_type("text/javascript", ".mjs")

ROOT = Path(__file__).resolve().parents[1]
GLOBE_HOST = "globe.localhost"
OSIRIS_HOST = "osiris.localhost"

_HOP_BY_HOP = frozenset(
    {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
     "transfer-encoding", "upgrade"}
)
# OSIRIS allows framing only by its own origin. The dashboard that embeds it is a
# different host name, so those two headers would block the embed for no benefit
# on a private loopback server.
_OSIRIS_STRIPPED = frozenset({"x-frame-options", "strict-transport-security"})


@dataclass(frozen=True)
class Config:
    dashboard_port: int
    osiris_port: int | None = None
    globe_dir: Path = ROOT / "holo-view-maker" / ".output" / "public"
    # Served ahead of the build's own copy, so a data refresh shows up in the
    # globe without rebuilding it.
    globe_data_dir: Path = ROOT / "holo-view-maker" / "public" / "data"
    upstream_host: str = "127.0.0.1"

    @classmethod
    def from_env(cls) -> "Config":
        osiris = os.getenv("GATEWAY_OSIRIS_PORT")
        return cls(
            dashboard_port=int(os.environ["GATEWAY_DASH_PORT"]),
            osiris_port=int(osiris) if osiris else None,
            globe_dir=Path(os.getenv("GATEWAY_GLOBE_DIR") or cls.globe_dir),
            globe_data_dir=Path(os.getenv("GATEWAY_GLOBE_DATA_DIR") or cls.globe_data_dir),
        )


def target_for(host_header: str) -> str:
    """Which program a request is for: "globe", "osiris" or "dashboard"."""
    host = (urlsplit("//" + host_header).hostname or "").lower()
    if host == GLOBE_HOST:
        return "globe"
    if host == OSIRIS_HOST:
        return "osiris"
    return "dashboard"


def _unavailable(title: str, detail: str, *, retry: bool) -> HTMLResponse:
    refresh = '<meta http-equiv="refresh" content="2">' if retry else ""
    page = (
        f'<!doctype html><meta charset="utf-8">{refresh}<title>{title}</title>'
        '<body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#0a0e13;'
        'color:#e4eaf0;font:15px/1.5 system-ui,sans-serif"><div style="max-width:28rem;padding:1.5rem">'
        f'<p style="font-weight:600;margin:0 0 .4rem">{title}</p>'
        f'<p style="margin:0;color:#a1adba">{detail}</p></div></body>'
    )
    return HTMLResponse(page, status_code=503)


def _starting(name: str) -> HTMLResponse:
    return _unavailable(f"{name} is starting", "This page reloads by itself as soon as it is ready.", retry=True)


# --------------------------------------------------------------- the globe --


def _safe_file(base: Path, rel: str) -> Path | None:
    """`rel` under `base`, or None. Refuses anything that resolves outside it."""
    try:
        root = base.resolve()
        candidate = (root / rel).resolve()
    except OSError:
        return None
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def _globe_response(config: Config, path: str) -> Response:
    index = config.globe_dir / "index.html"
    if not index.is_file():
        return _unavailable(
            "The 3D globe has not been built",
            "Run python start_all.py, or npm run build inside holo-view-maker.",
            retry=False,
        )
    rel = path.lstrip("/")
    found: Path | None = None
    if rel.startswith("data/"):
        found = _safe_file(config.globe_data_dir, rel[len("data/"):])
    if found is None and rel:
        found = _safe_file(config.globe_dir, rel)
    if found is None:
        if Path(rel).suffix:  # a missing file, not a route
            return Response("Not found", status_code=404, media_type="text/plain")
        found = index  # the app is a single page
    hashed = rel.startswith(("assets/", "vendor/"))
    cache = "public, max-age=31536000, immutable" if hashed else "no-cache"
    return FileResponse(found, headers={"Cache-Control": cache})


# ------------------------------------------------------------------- proxy --


def _rewrite_location(value: str, upstream_origin: str, request: Request) -> str:
    if value.startswith(upstream_origin):
        host = request.headers.get("host", "")
        return f"{request.url.scheme}://{host}{value[len(upstream_origin):]}"
    return value


async def _proxy_http(request: Request, name: str, port: int, strip: frozenset[str] = frozenset()) -> Response:
    config: Config = request.app.state.config
    client: httpx.AsyncClient = request.app.state.client
    origin = f"http://{config.upstream_host}:{port}"
    raw_path = (request.scope.get("raw_path") or request.url.path.encode()).decode("latin-1")
    url = origin + raw_path + (f"?{request.url.query}" if request.url.query else "")

    headers = [
        (k, v)
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP and k.lower() not in {"host", "origin"}
    ]
    headers.append(("host", f"{config.upstream_host}:{port}"))
    if "origin" in request.headers:
        headers.append(("origin", origin))
    client_ip = request.client.host if request.client else "127.0.0.1"
    headers += [
        ("x-forwarded-for", client_ip),
        ("x-forwarded-host", request.headers.get("host", "")),
        ("x-forwarded-proto", request.url.scheme),
    ]

    has_body = request.method not in {"GET", "HEAD", "OPTIONS"}
    upstream_request = client.build_request(
        request.method, url, headers=headers, content=request.stream() if has_body else None
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return _starting(name)

    out: list[tuple[bytes, bytes]] = []
    for key, value in upstream.headers.multi_items():
        lower = key.lower()
        if lower in _HOP_BY_HOP or lower in strip:
            continue
        if lower == "location":
            value = _rewrite_location(value, origin, request)
        out.append((lower.encode("latin-1"), value.encode("latin-1")))

    # Raw bytes, so compression and length stay exactly as the upstream sent them.
    response = StreamingResponse(
        upstream.aiter_raw(), status_code=upstream.status_code, background=BackgroundTask(upstream.aclose)
    )
    response.raw_headers = out
    return response


async def _proxy_ws(websocket: WebSocket, port: int) -> None:
    config: Config = websocket.app.state.config
    origin = f"http://{config.upstream_host}:{port}"
    query = websocket.url.query
    uri = f"ws://{config.upstream_host}:{port}{websocket.url.path}" + (f"?{query}" if query else "")
    extra = {"Origin": origin}
    if "cookie" in websocket.headers:
        extra["Cookie"] = websocket.headers["cookie"]
    subprotocols = websocket.scope.get("subprotocols") or None

    try:
        async with websockets.connect(
            uri, additional_headers=extra, subprotocols=subprotocols, max_size=None, open_timeout=10
        ) as upstream:
            await websocket.accept(subprotocol=upstream.subprotocol)

            async def to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def to_client() -> None:
                async for data in upstream:
                    if isinstance(data, str):
                        await websocket.send_text(data)
                    else:
                        await websocket.send_bytes(data)

            tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.exception()  # a dropped connection ends the pair; it is not an error worth raising
    except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError):
        pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass  # already closed


# ------------------------------------------------------------------ routes --


async def _http(request: Request) -> Response:
    config: Config = request.app.state.config
    target = target_for(request.headers.get("host", ""))
    if target == "globe":
        if request.method not in {"GET", "HEAD"}:
            return Response(status_code=405, headers={"Allow": "GET, HEAD"})
        return _globe_response(config, request.url.path)
    if target == "osiris":
        if config.osiris_port is None:
            return _unavailable("OSIRIS is not running", "It was left out when the platform was started.", retry=False)
        return await _proxy_http(request, "OSIRIS", config.osiris_port, _OSIRIS_STRIPPED)
    return await _proxy_http(request, "The dashboard", config.dashboard_port)


async def _websocket(websocket: WebSocket) -> None:
    config: Config = websocket.app.state.config
    target = target_for(websocket.headers.get("host", ""))
    port = config.osiris_port if target == "osiris" else config.dashboard_port if target == "dashboard" else None
    if port is None:
        await websocket.close(code=1008)
        return
    await _proxy_ws(websocket, port)


async def _is_up(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=0.6)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    return True


async def _health(request: Request) -> Response:
    config: Config = request.app.state.config
    return JSONResponse(
        {
            "dashboard": await _is_up(config.upstream_host, config.dashboard_port),
            "osiris": None if config.osiris_port is None else await _is_up(config.upstream_host, config.osiris_port),
            "globe": (config.globe_dir / "index.html").is_file(),
        }
    )


def create_app(config: Config) -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        # No read timeout: Streamlit and Next both hold long-lived responses open.
        app.state.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=None),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        )
        try:
            yield
        finally:
            await app.state.client.aclose()

    app = Starlette(
        routes=[
            Route("/__gateway/health", _health),
            WebSocketRoute("/{path:path}", _websocket),
            Route("/{path:path}", _http, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        ],
        lifespan=lifespan,
    )
    app.state.config = config
    return app


def create_app_from_env() -> Starlette:
    return create_app(Config.from_env())
