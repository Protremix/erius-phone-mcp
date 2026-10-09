"""Offline tests for erius-phone-mcp: no live device or network needed.

HTTP is intercepted by swapping the server module's httpx.Client for one
bound to an httpx.MockTransport. Tool calls go through a real in-memory
FastMCP client, so these also check what an MCP client actually receives.
"""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import erius_phone_mcp
from erius_phone_mcp import server

BASE = "https://api.test.invalid"
KEY = "sdk_test_key"

EXPECTED_TOOLS = {
    "list_devices", "whoami", "get_device",
    "snapshot", "screenshot", "foreground",
    "tap", "long_press", "type_text", "press_key", "swipe", "scroll", "wait_for_text",
    "launch_app", "open_url", "send_intent", "stop_app", "list_apps", "uninstall_app",
    "get_crash_log", "install_apk",
}

ENV_VARS = tuple(server._LEGACY_ENV) + tuple(server._LEGACY_ENV.values())


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start every test with none of the ERIUS_* vars set, whatever the shell has."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ERIUS_PHONE_API_URL", BASE)
    monkeypatch.setenv("ERIUS_PHONE_API_KEY", KEY)


@pytest.fixture
def mock_api(monkeypatch):
    """Route all httpx traffic to a handler; returns the list of captured requests.

    Set `mock_api.handler` to change the response (default: 200 {"ok": true}).
    """
    class State(list):
        handler = staticmethod(lambda req: httpx.Response(200, json={"ok": True}))

    state = State()

    def transport_handler(request: httpx.Request) -> httpx.Response:
        state.append(request)
        return state.handler(request)

    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(transport_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    return state


def call(name: str, args: dict | None = None):
    """Call a tool through an in-memory MCP client and return its structured result."""
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(name, args or {})
    return asyncio.run(go())


def call_error(name: str, args: dict | None = None) -> str:
    """Call a tool expecting failure; return the error text the MCP client sees."""
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(name, args or {}, raise_on_error=False)
    result = asyncio.run(go())
    assert result.is_error, f"{name} unexpectedly succeeded: {result}"
    return result.content[0].text


# ---------- registration ----------

def test_all_21_tools_registered():
    async def go():
        async with Client(server.mcp) as c:
            return await c.list_tools()
    tools = asyncio.run(go())
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS
    assert len(tools) == 21
    for t in tools:
        assert t.description and t.description.strip(), f"{t.name} has no description"


def test_package_exports():
    assert erius_phone_mcp.mcp is server.mcp
    assert callable(erius_phone_mcp.main)
    assert erius_phone_mcp.__version__ == "0.1.1"


# ---------- ERIUS_PHONE_API_URL ----------

def test_base_url_defaults_to_production(monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_API_KEY", KEY)
    call("list_devices")
    assert str(mock_api[0].url) == "https://api.eriusphone.com/devices"


def test_blank_base_url_uses_default(monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_API_URL", "   ")
    monkeypatch.setenv("ERIUS_PHONE_API_KEY", KEY)
    call("list_devices")
    assert str(mock_api[0].url) == "https://api.eriusphone.com/devices"


def test_missing_key_checked_before_any_request(mock_api):
    msg = call_error("get_device", {"device": "vanilla"})
    assert "ERIUS_PHONE_API_KEY is not set" in msg
    assert mock_api == []


def test_base_url_without_scheme_rejected(monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_API_URL", "api.example.com")
    monkeypatch.setenv("ERIUS_PHONE_API_KEY", KEY)
    msg = call_error("list_devices")
    assert "must start with http:// or https://" in msg
    assert mock_api == []


def test_install_apk_requires_key(tmp_path, mock_api):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK\x03\x04")
    msg = call_error("install_apk", {"apk_path": str(apk), "device": "vanilla"})
    assert "ERIUS_PHONE_API_KEY is not set" in msg
    assert mock_api == []


def test_base_url_trailing_slash_stripped(monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_API_URL", BASE + "/")
    monkeypatch.setenv("ERIUS_PHONE_API_KEY", KEY)
    call("list_devices")
    assert str(mock_api[0].url) == f"{BASE}/devices"


def test_unreachable_api_gives_clear_error(configured, mock_api):
    def refuse(req):
        raise httpx.ConnectError("[Errno 111] Connection refused", request=req)
    mock_api.handler = refuse
    msg = call_error("list_devices")
    assert f"could not reach the ERIUS PHONE API at {BASE}" in msg
    assert "ERIUS_PHONE_API_URL" in msg


def test_main_warns_on_stderr_when_unset(monkeypatch, capsys):
    monkeypatch.setattr(server.mcp, "run", lambda *a, **k: None)
    server.main()
    err = capsys.readouterr().err
    assert "ERIUS_PHONE_API_URL" not in err  # has a default now
    assert "ERIUS_PHONE_API_KEY is not set" in err


def test_main_quiet_when_configured(configured, monkeypatch, capsys):
    monkeypatch.setattr(server.mcp, "run", lambda *a, **k: None)
    server.main()
    assert capsys.readouterr().err == ""


def test_legacy_env_names_still_work(monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_API_BASE_URL", BASE)
    monkeypatch.setenv("ERIUS_API_KEY", KEY)
    monkeypatch.setenv("ERIUS_DEFAULT_DEVICE", "vanilla")
    call("foreground")
    assert str(mock_api[0].url) == f"{BASE}/device/vanilla/foreground"
    assert mock_api[0].headers["X-API-Key"] == KEY


def test_new_env_name_wins_over_legacy(configured, monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_API_KEY", "old_key")
    call("whoami")
    assert mock_api[0].headers["X-API-Key"] == KEY


# ---------- _headers() / auth ----------

def test_headers_without_key_raises():
    with pytest.raises(ToolError, match="ERIUS_PHONE_API_KEY is not set"):
        server._headers()


def test_headers_with_key(monkeypatch):
    monkeypatch.setenv("ERIUS_PHONE_API_KEY", KEY)
    assert server._headers() == {"X-API-Key": KEY, "Accept": "application/json"}


def test_missing_key_surfaces_through_tool_call(monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_API_URL", BASE)
    msg = call_error("list_devices")
    assert "ERIUS_PHONE_API_KEY is not set" in msg
    assert mock_api == []


def test_api_key_sent_on_every_request(configured, mock_api):
    call("list_devices")
    call("press_key", {"key": "home", "device": "vanilla"})
    assert [r.headers["X-API-Key"] for r in mock_api] == [KEY, KEY]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejection_is_reported(configured, mock_api, status):
    mock_api.handler = lambda req: httpx.Response(status, json={"error": "unauthorized"})
    msg = call_error("list_devices")
    assert f"HTTP {status}" in msg
    assert "unauthorized" in msg


def test_install_apk_auth_rejection_is_an_error(configured, tmp_path, mock_api):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK\x03\x04")
    mock_api.handler = lambda req: httpx.Response(401, json={"error": "unauthorized"})
    msg = call_error("install_apk", {"apk_path": str(apk), "device": "vanilla"})
    assert "HTTP 401" in msg


def test_install_apk_adb_failure_returns_body(configured, tmp_path, mock_api):
    # 422 = adb ran but refused the APK; that detail is the useful result.
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK\x03\x04")
    mock_api.handler = lambda req: httpx.Response(
        422, json={"ok": False, "error": "INSTALL_FAILED_VERSION_DOWNGRADE"})
    result = call("install_apk", {"apk_path": str(apk), "device": "vanilla", "allow_downgrade": True})
    assert result.structured_content == {"ok": False, "error": "INSTALL_FAILED_VERSION_DOWNGRADE"}
    req = mock_api[0]
    assert req.url.path == "/device/vanilla/install"
    assert req.url.params["downgrade"] == "1"
    assert req.headers["Content-Type"] == "application/vnd.android.package-archive"
    assert req.content == b"PK\x03\x04"


# ---------- request shaping ----------

def test_default_device_used_when_omitted(configured, monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_DEFAULT_DEVICE", "vanilla")
    call("foreground")
    assert mock_api[0].url.path == "/device/vanilla/foreground"


def test_no_device_and_no_default_errors(configured, mock_api):
    msg = call_error("foreground")
    assert "ERIUS_PHONE_DEFAULT_DEVICE is not set" in msg
    assert mock_api == []


def test_tap_by_ref_sends_json_body(configured, mock_api):
    call("tap", {"device": "vanilla", "ref": "5"})
    req = mock_api[0]
    assert (req.method, req.url.path) == ("POST", "/device/vanilla/tap")
    assert json.loads(req.content) == {"ref": "5"}


def test_tap_without_target_errors(configured, mock_api):
    assert "tap needs ref" in call_error("tap", {"device": "vanilla"})
    assert mock_api == []


def test_screenshot_returns_image_content(configured, mock_api):
    png = b"\x89PNG\r\n\x1a\nfake"
    mock_api.handler = lambda req: httpx.Response(200, content=png, headers={"content-type": "image/png"})
    content = call("screenshot", {"device": "vanilla"}).content
    assert len(content) == 1 and content[0].type == "image"
    assert content[0].mime_type == "image/png"
    assert base64.b64decode(content[0].data) == png


def test_bad_timeout_env_is_clear(configured, monkeypatch, mock_api):
    monkeypatch.setenv("ERIUS_PHONE_TIMEOUT", "thirty")
    assert "ERIUS_PHONE_TIMEOUT must be a number" in call_error("list_devices")


def test_long_press_xy_with_ms(configured, mock_api):
    call("long_press", {"device": "vanilla", "x": 10, "y": 20, "ms": 1200})
    req = mock_api[0]
    assert (req.method, req.url.path) == ("POST", "/device/vanilla/longpress")
    assert json.loads(req.content) == {"x": 10, "y": 20, "ms": 1200}


def test_long_press_by_text(configured, mock_api):
    call("long_press", {"device": "vanilla", "text": "Chrome"})
    assert json.loads(mock_api[0].content) == {"text": "Chrome"}


def test_long_press_without_target_errors(configured, mock_api):
    assert "long_press needs ref" in call_error("long_press", {"device": "vanilla"})
    assert mock_api == []


def test_send_intent_omits_unset_fields(configured, mock_api):
    call("send_intent", {"device": "vanilla", "action": "android.settings.WIFI_SETTINGS",
                         "extras": {"n": 1, "flag": True, "s": "x"}})
    req = mock_api[0]
    assert (req.method, req.url.path) == ("POST", "/device/vanilla/intent")
    assert json.loads(req.content) == {"action": "android.settings.WIFI_SETTINGS",
                                       "extras": {"n": 1, "flag": True, "s": "x"}}


def test_whoami_hits_whoami(configured, mock_api):
    call("whoami")
    assert (mock_api[0].method, mock_api[0].url.path) == ("GET", "/whoami")


def test_scroll_sends_container_ref(configured, mock_api):
    call("scroll", {"device": "vanilla", "direction": "down", "ref": "3"})
    req = mock_api[0]
    assert (req.method, req.url.path) == ("POST", "/device/vanilla/scroll")
    assert json.loads(req.content) == {"direction": "down", "ref": "3"}


def test_api_error_body_is_formatted(configured, mock_api):
    mock_api.handler = lambda req: httpx.Response(404, json={
        "ok": False, "error": "SelectorNotFound", "message": 'nothing on screen matches {"text":"Nope"}',
        "requestId": "abc123"})
    msg = call_error("tap", {"device": "vanilla", "text": "Nope"})
    assert msg == ('device-api POST /device/vanilla/tap -> HTTP 404 SelectorNotFound: '
                   'nothing on screen matches {"text":"Nope"} (requestId abc123)')


def test_non_json_error_body_is_passed_through(configured, mock_api):
    mock_api.handler = lambda req: httpx.Response(502, text="<html>Bad Gateway</html>")
    assert call_error("list_devices").endswith("HTTP 502: <html>Bad Gateway</html>")
