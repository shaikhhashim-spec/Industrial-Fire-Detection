from unittest.mock import MagicMock, patch

import pytest

from src.alerts import dispatch


@pytest.fixture(autouse=True)
def _clear_config(monkeypatch):
    for attr in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "ALERT_SMS_TO_NUMBER",
                 "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "ALERT_WEBHOOK_URL"):
        monkeypatch.setattr(dispatch.config, attr, "")
    yield


def _configure_twilio(monkeypatch):
    monkeypatch.setattr(dispatch.config, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(dispatch.config, "TWILIO_AUTH_TOKEN", "authtoken")
    monkeypatch.setattr(dispatch.config, "TWILIO_FROM_NUMBER", "+10000000000")
    monkeypatch.setattr(dispatch.config, "ALERT_SMS_TO_NUMBER", "+19999999999")


def _configure_telegram(monkeypatch):
    monkeypatch.setattr(dispatch.config, "TELEGRAM_BOT_TOKEN", "bottoken")
    monkeypatch.setattr(dispatch.config, "TELEGRAM_CHAT_ID", "12345")


def _configure_webhook(monkeypatch):
    monkeypatch.setattr(dispatch.config, "ALERT_WEBHOOK_URL", "https://example.com/hook")


# --- configured_* helpers -----------------------------------------------------

def test_none_configured_by_default():
    assert not dispatch.sms_configured()
    assert not dispatch.telegram_configured()
    assert not dispatch.webhook_configured()


def test_sms_configured_requires_all_four_fields(monkeypatch):
    monkeypatch.setattr(dispatch.config, "TWILIO_ACCOUNT_SID", "AC123")
    assert not dispatch.sms_configured()  # only one of four set
    _configure_twilio(monkeypatch)
    assert dispatch.sms_configured()


# --- send_sms ------------------------------------------------------------------

def test_send_sms_not_configured_returns_ok_false_without_network_call():
    with patch.object(dispatch.requests, "post") as mock_post:
        result = dispatch.send_sms("test body")
    mock_post.assert_not_called()
    assert result["ok"] is False
    assert "not configured" in result["detail"].lower()


def test_send_sms_success(monkeypatch):
    _configure_twilio(monkeypatch)
    mock_resp = MagicMock(ok=True)
    mock_resp.json.return_value = {"sid": "SM123abc"}
    with patch.object(dispatch.requests, "post", return_value=mock_resp) as mock_post:
        result = dispatch.send_sms("test body")
    assert result["ok"] is True
    assert "SM123abc" in result["detail"]
    args, kwargs = mock_post.call_args
    assert kwargs["auth"] == ("AC123", "authtoken")
    assert kwargs["data"]["To"] == "+19999999999"
    assert kwargs["data"]["Body"] == "test body"


def test_send_sms_http_error(monkeypatch):
    _configure_twilio(monkeypatch)
    mock_resp = MagicMock(ok=False, status_code=401, text="Unauthorized")
    with patch.object(dispatch.requests, "post", return_value=mock_resp):
        result = dispatch.send_sms("test body")
    assert result["ok"] is False
    assert "401" in result["detail"]


def test_send_sms_network_exception(monkeypatch):
    _configure_twilio(monkeypatch)
    with patch.object(dispatch.requests, "post", side_effect=dispatch.requests.exceptions.ConnectionError("down")):
        result = dispatch.send_sms("test body")
    assert result["ok"] is False
    assert "failed" in result["detail"].lower()


# --- send_telegram ---------------------------------------------------------

def test_send_telegram_not_configured_without_network_call():
    with patch.object(dispatch.requests, "post") as mock_post:
        result = dispatch.send_telegram("test text")
    mock_post.assert_not_called()
    assert result["ok"] is False


def test_send_telegram_success(monkeypatch):
    _configure_telegram(monkeypatch)
    mock_resp = MagicMock(ok=True, headers={"content-type": "application/json"})
    mock_resp.json.return_value = {"ok": True}
    with patch.object(dispatch.requests, "post", return_value=mock_resp) as mock_post:
        result = dispatch.send_telegram("test text")
    assert result["ok"] is True
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "test text"


def test_send_telegram_api_rejection(monkeypatch):
    _configure_telegram(monkeypatch)
    mock_resp = MagicMock(ok=True, headers={"content-type": "application/json"})
    mock_resp.json.return_value = {"ok": False, "description": "chat not found"}
    with patch.object(dispatch.requests, "post", return_value=mock_resp):
        result = dispatch.send_telegram("test text")
    assert result["ok"] is False
    assert "chat not found" in result["detail"]


# --- send_webhook ------------------------------------------------------------

def test_send_webhook_not_configured_without_network_call():
    with patch.object(dispatch.requests, "post") as mock_post:
        result = dispatch.send_webhook({"a": 1})
    mock_post.assert_not_called()
    assert result["ok"] is False


def test_send_webhook_success(monkeypatch):
    _configure_webhook(monkeypatch)
    mock_resp = MagicMock(ok=True, status_code=200)
    with patch.object(dispatch.requests, "post", return_value=mock_resp) as mock_post:
        result = dispatch.send_webhook({"event_id": "TH-123"})
    assert result["ok"] is True
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.com/hook"
    assert kwargs["json"] == {"event_id": "TH-123"}


def test_send_webhook_http_error(monkeypatch):
    _configure_webhook(monkeypatch)
    mock_resp = MagicMock(ok=False, status_code=500, text="server error")
    with patch.object(dispatch.requests, "post", return_value=mock_resp):
        result = dispatch.send_webhook({"event_id": "TH-123"})
    assert result["ok"] is False
    assert "500" in result["detail"]
