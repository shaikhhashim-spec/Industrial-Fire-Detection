import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.websockets import WebSocketDisconnect

from gateway.app import Config, _proxy_ws


def test_dropped_browser_does_not_raise_during_gateway_cleanup():
    websocket = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(config=Config(dashboard_port=1))),
        url=SimpleNamespace(query="", path="/_stcore/stream"), headers={}, scope={},
        close=AsyncMock(side_effect=WebSocketDisconnect(code=1006)),
    )
    with patch("gateway.app.websockets.connect", side_effect=OSError("Disconnected")):
        asyncio.run(_proxy_ws(websocket))
    websocket.close.assert_awaited_once()
