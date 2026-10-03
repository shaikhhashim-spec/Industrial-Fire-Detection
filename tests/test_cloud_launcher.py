"""Cloud regression checks: mocked processes, clocks, signals, and network."""
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import cloud_launcher as launcher
import start_all


@pytest.fixture
def cloud_env(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.os, "environ", {})
    for name in ("GATEWAY_SITE_DIR", "GATEWAY_GLOBE_DIR"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "index.html").write_text("built", encoding="ascii")
        monkeypatch.setenv(name, str(folder))
    monkeypatch.setenv("THERMAL_ADMIN_PASSWORD", "test-only-password")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@db/thermal")


def test_cloud_contract(cloud_env, monkeypatch):
    monkeypatch.setenv("PORT", "12345")
    port, env = launcher.cloud_environment()
    assert port == 12345
    assert env["CLOUD_MODE"] == "true"
    assert env["GLOBE_URL"] == "/globe"
    assert env["ALERT_AUTO_DISPATCH_CRITICAL"] == "false"
    commands = launcher.child_commands(port, 9000)
    assert commands[0][commands[0].index("--server.address") + 1] == "127.0.0.1"
    assert commands[0][commands[0].index("--server.baseUrlPath") + 1] == "console"
    assert commands[1][commands[1].index("--host") + 1] == "0.0.0.0"
    assert commands[1][commands[1].index("--port") + 1] == "12345"
    assert start_all.DEFAULT_PORT == 8085


@pytest.mark.parametrize("database", ["", "sqlite:///local.db", "postgresql:///missing-host"])
def test_production_requires_postgres(cloud_env, monkeypatch, database):
    monkeypatch.setenv("DATABASE_URL", database)
    with pytest.raises(ValueError, match="PostgreSQL"):
        launcher.cloud_environment()


def test_demo_allows_ephemeral_sqlite(cloud_env, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.setenv("THERMAL_DEMO_MODE", "true")
    monkeypatch.setenv("JOBS_ENABLED", "true")
    monkeypatch.setenv("THERMAL_SCHEDULER_ENABLED", "1")
    env = launcher.cloud_environment()[1]
    assert env["THERMAL_DEMO_MODE"] == "true"
    assert env["JOBS_ENABLED"] == "false"
    assert env["THERMAL_SCHEDULER_ENABLED"] == "0"


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_port(cloud_env, monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ValueError):
        launcher.cloud_environment()


def test_missing_password_or_build_fails(cloud_env, monkeypatch):
    monkeypatch.delenv("THERMAL_ADMIN_PASSWORD")
    with pytest.raises(ValueError, match="PASSWORD"):
        launcher.cloud_environment()
    monkeypatch.setenv("THERMAL_ADMIN_PASSWORD", "test-password-long")
    (Path(launcher.os.environ["GATEWAY_GLOBE_DIR"]) / "index.html").unlink()
    with pytest.raises(ValueError, match="prebuilt"):
        launcher.cloud_environment()


def mock_runtime(monkeypatch):
    children = [Mock(), Mock()]
    for child in children:
        child.poll.return_value = None
    popen = Mock(side_effect=children)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    monkeypatch.setattr(launcher, "free_port", lambda: 9000)
    monkeypatch.setattr(launcher.time, "sleep", Mock())
    monkeypatch.setattr(launcher, "gateway_health", Mock(return_value=None))
    return children, popen


def test_timeout_cleans_children_without_startup_work(monkeypatch):
    children, popen = mock_runtime(monkeypatch)
    assert launcher.supervise(10000, {"CLOUD_MODE": "true"}, timeout=0) == 1
    assert popen.call_count == 2
    for call in popen.call_args_list:
        assert call.kwargs["env"]["GATEWAY_DASH_PORT"] == "9000"
        assert all("npm" not in word and "refresh" not in word for word in call.args[0])
    for child in children:
        child.terminate.assert_called_once()
        child.wait.assert_called_once()


def test_child_failure_stops_sibling(monkeypatch):
    children, _ = mock_runtime(monkeypatch)
    children[0].poll.return_value = 2
    assert launcher.supervise(10000, {}, timeout=0) == 1
    children[1].terminate.assert_called_once()


def test_signal_shutdown_restores_handlers(monkeypatch):
    children, _ = mock_runtime(monkeypatch)
    handlers = {}
    restored = []

    def register(sig, handler):
        if callable(handler):
            handlers[sig] = handler
        else:
            restored.append(sig)
        return signal.SIG_DFL

    monkeypatch.setattr(launcher.signal, "signal", register)
    monkeypatch.setattr(launcher, "gateway_health", lambda port: {"ready": True})
    monkeypatch.setattr(launcher.time, "sleep", lambda delay: handlers[signal.SIGTERM](None, None))
    assert launcher.supervise(10000, {}) == 0
    assert set(restored) == {signal.SIGINT, signal.SIGTERM}
    for child in children:
        child.terminate.assert_called_once()


def test_unresponsive_child_is_killed_and_reaped():
    child = Mock()
    child.poll.return_value = None
    child.wait.side_effect = [subprocess.TimeoutExpired("test", 10), 0]
    launcher.stop_children([child])
    child.kill.assert_called_once()
    assert child.wait.call_count == 2


def test_partial_spawn_failure_stops_started_child(monkeypatch):
    children, popen = mock_runtime(monkeypatch)
    popen.side_effect = [children[0], OSError("spawn failed")]
    with pytest.raises(OSError):
        launcher.supervise(10000, {})
    children[0].terminate.assert_called_once()


def test_main_passes_cloud_env_and_restores_parent(cloud_env, monkeypatch):
    original = launcher.os.environ.copy()

    def config_from_env():
        assert launcher.os.environ["CLOUD_MODE"] == "true"
        assert launcher.os.environ["GATEWAY_DASH_PORT"] == "1"
        return SimpleNamespace(cloud_mode=True)

    monkeypatch.setitem(sys.modules, "gateway.app", SimpleNamespace(
        Config=SimpleNamespace(from_env=config_from_env)))
    supervise = Mock(return_value=0)
    monkeypatch.setattr(launcher, "supervise", supervise)
    assert launcher.main() == 0
    assert launcher.os.environ == original
    env = supervise.call_args.args[1]
    assert env["THERMAL_ADMIN_USERNAME"] == "admin"
    assert env["THERMAL_SERVER_DB"].endswith("server.db")


def test_main_refuses_old_gateway_before_spawning(cloud_env, monkeypatch):
    monkeypatch.setitem(sys.modules, "gateway.app", SimpleNamespace(
        Config=SimpleNamespace(from_env=lambda: SimpleNamespace())))
    supervise = Mock()
    monkeypatch.setattr(launcher, "supervise", supervise)
    assert launcher.main() == 1
    supervise.assert_not_called()
