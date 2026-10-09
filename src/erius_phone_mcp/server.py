"""ERIUS PHONE MCP server — control a real Android device as an MCP tool surface.

Wraps the device-api HTTP service (server.mjs) so any MCP client (Claude Code,
Claude Desktop, Cursor, etc.) can list devices, read the screen, and drive
taps/typing/app installs on a real Android phone given to an agent.

Env vars (the older ERIUS_* names without PHONE_ are still accepted):
  ERIUS_PHONE_API_KEY        required — your ERIUS PHONE API key
  ERIUS_PHONE_API_URL        optional — default https://api.eriusphone.com
  ERIUS_PHONE_DEFAULT_DEVICE optional — device id to use when a tool call omits one
  ERIUS_PHONE_TIMEOUT        default 30 (seconds)
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image

from . import __version__

mcp = FastMCP("erius-phone", version=__version__)

DEFAULT_BASE_URL = "https://api.eriusphone.com"

# Config is read from the environment on every call (not at import) so a
# missing or bad variable produces a clear tool error.

# Documented name -> pre-release name, still accepted as a fallback.
_LEGACY_ENV = {
    "ERIUS_PHONE_API_KEY": "ERIUS_API_KEY",
    "ERIUS_PHONE_API_URL": "ERIUS_API_BASE_URL",
    "ERIUS_PHONE_DEFAULT_DEVICE": "ERIUS_DEFAULT_DEVICE",
    "ERIUS_PHONE_TIMEOUT": "ERIUS_API_TIMEOUT",
}


def _env(name: str) -> str:
    return (os.getenv(name) or os.getenv(_LEGACY_ENV[name]) or "").strip()


def _base_url() -> str:
    url = _env("ERIUS_PHONE_API_URL") or DEFAULT_BASE_URL
    if not url.startswith(("http://", "https://")):
        raise ToolError(f"ERIUS_PHONE_API_URL must start with http:// or https:// (got {url!r})")
    return url.rstrip("/")


def _timeout() -> float:
    raw = _env("ERIUS_PHONE_TIMEOUT") or "30"
    try:
        return float(raw)
    except ValueError:
        raise ToolError(f"ERIUS_PHONE_TIMEOUT must be a number of seconds (got {raw!r})") from None


def _headers() -> dict[str, str]:
    key = _env("ERIUS_PHONE_API_KEY")
    if not key:
        raise ToolError(
            "ERIUS_PHONE_API_KEY is not set — set it to your ERIUS PHONE API key in your MCP client's `env` block"
        )
    return {"X-API-Key": key, "Accept": "application/json"}


def _request(method: str, path: str, *, params: dict[str, Any] | None = None,
             json_body: dict[str, Any] | None = None) -> httpx.Response:
    url = f"{_base_url()}/{path.lstrip('/')}"
    with httpx.Client(timeout=_timeout(), headers=_headers()) as client:
        try:
            resp = client.request(method, url, params=params, json=json_body)
        except httpx.TransportError as e:
            raise ToolError(
                f"could not reach the ERIUS PHONE API at {_base_url()} ({type(e).__name__}: {e}) — "
                "check ERIUS_PHONE_API_URL, or raise ERIUS_PHONE_TIMEOUT on a slow link"
            ) from e
    if resp.status_code >= 400:
        raise ToolError(f"device-api {method} {path} -> {_error_text(resp)}")
    return resp


def _error_text(resp: httpx.Response) -> str:
    """'HTTP 404 SelectorNotFound: <message> (requestId ...)' from the API's
    {"error", "message", "requestId"} body; raw body if it isn't that shape."""
    try:
        body = resp.json()
    except Exception:
        body = None
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        text = f"HTTP {resp.status_code} {body.get('error', 'error')}: {body['message']}"
        return f"{text} (requestId {body['requestId']})" if body.get("requestId") else text
    return f"HTTP {resp.status_code}: {body if body is not None else resp.text.strip()[:500]}"


def _json(method: str, path: str, **kw: Any) -> Any:
    return _request(method, path, **kw).json()


def _device_id(device: Optional[str]) -> str:
    d = device or _env("ERIUS_PHONE_DEFAULT_DEVICE")
    if not d:
        raise ToolError("no device id given and ERIUS_PHONE_DEFAULT_DEVICE is not set — call list_devices() first")
    return d


# ---------- discovery ----------

@mcp.tool
def list_devices() -> dict[str, Any]:
    """List every Android device your API key can access, with live status
    (booted, Android version, screen size). Call this first to get device ids."""
    return _json("GET", "/devices")


@mcp.tool
def whoami() -> dict[str, Any]:
    """Show which ERIUS PHONE account (tenant) and key id this server is using,
    and the device ids it can access. Handy to check the API key works."""
    return _json("GET", "/whoami")


@mcp.tool
def get_device(device: Optional[str] = None) -> dict[str, Any]:
    """Get full status of one device: boot state, Android version, screen size,
    and the app currently in the foreground. Omit `device` to use the default."""
    return _json("GET", f"/device/{_device_id(device)}")


# ---------- seeing the screen ----------

@mcp.tool
def snapshot(device: Optional[str] = None, max_depth: Optional[int] = None,
             max_nodes: Optional[int] = None) -> dict[str, Any]:
    """Get an accessibility-tree snapshot of the current screen: every visible
    element with its text, role, and a `ref` id you can pass to tap/type/scroll.
    This is how the agent 'sees' the phone — read it before acting, and take a
    fresh one after any action since refs reset on every snapshot."""
    params: dict[str, Any] = {}
    if max_depth is not None:
        params["maxDepth"] = max_depth
    if max_nodes is not None:
        params["maxNodes"] = max_nodes
    return _json("GET", f"/device/{_device_id(device)}/snapshot", params=params)


@mcp.tool
def screenshot(device: Optional[str] = None) -> Image:
    """Take a screenshot of the device screen right now (PNG at the device's
    native resolution, e.g. 720x1280 on a phone) and return it as an image you
    can look at. Tap coordinates are in the same pixels. Prefer snapshot()
    when you only need text and refs: it's far smaller."""
    resp = _request("GET", f"/device/{_device_id(device)}/screenshot")
    fmt = resp.headers.get("content-type", "image/png").split(";")[0].split("/")[-1] or "png"
    return Image(data=resp.content, format=fmt)


@mcp.tool
def foreground(device: Optional[str] = None) -> dict[str, Any]:
    """Get just the foreground app: package, activity, and whether a crash
    dialog is showing. Cheaper than a full snapshot when you only need this."""
    return _json("GET", f"/device/{_device_id(device)}/foreground")


# ---------- acting on the screen ----------

@mcp.tool
def tap(device: Optional[str] = None, ref: Optional[str] = None, text: Optional[str] = None,
        content_desc: Optional[str] = None, x: Optional[int] = None, y: Optional[int] = None) -> dict[str, Any]:
    """Tap an element. Prefer `ref` from a snapshot(), or `text`/`content_desc`
    to tap by visible label. Falls back to raw `x`,`y` pixel coordinates."""
    body: dict[str, Any] = {}
    if ref is not None:
        body["ref"] = ref
    elif text is not None or content_desc is not None:
        if text is not None:
            body["text"] = text
        if content_desc is not None:
            body["contentDesc"] = content_desc
    elif x is not None and y is not None:
        body["x"], body["y"] = x, y
    else:
        raise ToolError("tap needs ref, or text/content_desc, or x and y")
    return _json("POST", f"/device/{_device_id(device)}/tap", json_body=body)


@mcp.tool
def long_press(device: Optional[str] = None, ref: Optional[str] = None, text: Optional[str] = None,
               content_desc: Optional[str] = None, x: Optional[int] = None, y: Optional[int] = None,
               ms: Optional[int] = None) -> dict[str, Any]:
    """Long-press an element (e.g. to open a context menu or start a drag).
    Targets work like tap(): `ref`, `text`/`content_desc`, or raw `x`,`y`.
    `ms` (hold time, default 800) only applies to the x,y form."""
    body: dict[str, Any] = {}
    if ref is not None:
        body["ref"] = ref
    elif text is not None or content_desc is not None:
        if text is not None:
            body["text"] = text
        if content_desc is not None:
            body["contentDesc"] = content_desc
    elif x is not None and y is not None:
        body["x"], body["y"] = x, y
        if ms is not None:
            body["ms"] = ms
    else:
        raise ToolError("long_press needs ref, or text/content_desc, or x and y")
    return _json("POST", f"/device/{_device_id(device)}/longpress", json_body=body)


@mcp.tool
def type_text(text: str, device: Optional[str] = None, ref: Optional[str] = None,
              text_target: Optional[str] = None, clear: bool = False, enter: bool = False) -> dict[str, Any]:
    """Type text into a field. Optionally tap a `ref` or `text_target` label
    first to focus the field, `clear` the existing value, or press Enter after.
    Keystrokes sent while the field is still opening are lost, so if tapping
    the field opens a new screen (e.g. a search page), tap it first, wait for
    it with snapshot() or wait_for_text(), then type with no target. Check the
    result with snapshot(). Only printable ASCII is supported (adb limitation)."""
    body: dict[str, Any] = {"text": text, "clear": clear, "enter": enter}
    if ref is not None:
        body["ref"] = ref
    if text_target is not None:
        body["target"] = {"text": text_target}
    return _json("POST", f"/device/{_device_id(device)}/type", json_body=body)


@mcp.tool
def press_key(key: str, device: Optional[str] = None) -> dict[str, Any]:
    """Press a hardware/navigation key: back, home, enter, delete, tab, escape,
    up, down, left, right, space, power, volup, voldown, recent, menu, wakeup."""
    return _json("POST", f"/device/{_device_id(device)}/press", json_body={"key": key})


@mcp.tool
def swipe(x1: int, y1: int, x2: int, y2: int, device: Optional[str] = None, ms: int = 300) -> dict[str, Any]:
    """Swipe from one point to another in device pixel coordinates."""
    return _json("POST", f"/device/{_device_id(device)}/swipe",
                 json_body={"x1": x1, "y1": y1, "x2": x2, "y2": y2, "ms": ms})


@mcp.tool
def scroll(direction: str, ref: str, device: Optional[str] = None) -> dict[str, Any]:
    """Scroll a list/container up, down, left, or right. `ref` must be the
    ref of the scrollable container itself (a ScrollView or List line in the
    snapshot), not of a row inside it: scrolling a single row does nothing.
    If the container has no ref, use swipe() instead."""
    # The API also accepts a text target, but it resolves to the matched row,
    # so the scroll happens inside that row and the list doesn't move. Only
    # the container ref is exposed here.
    return _json("POST", f"/device/{_device_id(device)}/scroll",
                 json_body={"direction": direction, "ref": ref})


@mcp.tool
def wait_for_text(text: str, device: Optional[str] = None, timeout_ms: int = 10_000) -> dict[str, Any]:
    """Wait until `text` appears somewhere on screen (e.g. after a slow screen
    transition), up to timeout_ms (max 120000). Returns the settled snapshot."""
    return _json("POST", f"/device/{_device_id(device)}/wait",
                 json_body={"text": text, "timeout": timeout_ms})


# ---------- apps ----------

@mcp.tool
def launch_app(package: str, device: Optional[str] = None, activity: Optional[str] = None) -> dict[str, Any]:
    """Launch an installed app by package name (e.g. com.android.chrome).
    Pass `activity` only if the app has no launcher activity resolvable automatically."""
    body: dict[str, Any] = {"package": package}
    if activity is not None:
        body["activity"] = activity
    return _json("POST", f"/device/{_device_id(device)}/launch", json_body=body)


@mcp.tool
def open_url(url: str, device: Optional[str] = None, package: Optional[str] = None) -> dict[str, Any]:
    """Open a URL (http/https/market) on the device, optionally forcing it
    into a specific app package (e.g. open a link in Chrome specifically)."""
    body: dict[str, Any] = {"url": url}
    if package is not None:
        body["package"] = package
    return _json("POST", f"/device/{_device_id(device)}/launch", json_body=body)


@mcp.tool
def send_intent(action: str, device: Optional[str] = None, data: Optional[str] = None,
                package: Optional[str] = None, component: Optional[str] = None,
                extras: Optional[dict[str, str | int | bool]] = None) -> dict[str, Any]:
    """Start an activity with an arbitrary Android intent (`am start -a ACTION`),
    e.g. action="android.settings.WIFI_SETTINGS" to jump straight to a settings
    page. `component` is "package/.Activity"; `extras` values become string,
    int or boolean extras by their type. Returns ok plus the new foreground app."""
    body: dict[str, Any] = {"action": action}
    for k, v in (("data", data), ("package", package), ("component", component), ("extras", extras)):
        if v is not None:
            body[k] = v
    return _json("POST", f"/device/{_device_id(device)}/intent", json_body=body)


@mcp.tool
def stop_app(package: str, device: Optional[str] = None) -> dict[str, Any]:
    """Force-stop a running app by package name."""
    return _json("POST", f"/device/{_device_id(device)}/stop", json_body={"package": package})


@mcp.tool
def list_apps(device: Optional[str] = None, third_party_only: bool = False) -> dict[str, Any]:
    """List installed apps on the device. Set third_party_only=True to skip
    pre-installed system apps and see only user-installed ones."""
    params = {"thirdParty": "1"} if third_party_only else None
    return _json("GET", f"/device/{_device_id(device)}/apps", params=params)


@mcp.tool
def uninstall_app(package: str, device: Optional[str] = None) -> dict[str, Any]:
    """Uninstall an app by package name."""
    return _json("DELETE", f"/device/{_device_id(device)}/apps/{package}")


@mcp.tool
def get_crash_log(device: Optional[str] = None, lines: int = 200) -> dict[str, Any]:
    """Read the device's crash log buffer (logcat -b crash) — use this after an
    app crashes during QA testing to see the real stack trace."""
    return _json("GET", f"/device/{_device_id(device)}/crashes", params={"lines": lines})


@mcp.tool
def install_apk(apk_path: str, device: Optional[str] = None, grant_permissions: bool = False,
                 allow_downgrade: bool = False) -> dict[str, Any]:
    """Install an APK from a local file path on the machine running this MCP
    server (not on the phone) onto the device. Use this for APK QA testing —
    the real use case ERIUS PHONE is built for. Returns the parsed package
    info (name, version) and whether the install actually succeeded."""
    if not os.path.isfile(apk_path):
        raise ToolError(f"no such file: {apk_path}")
    params: dict[str, Any] = {}
    if grant_permissions:
        params["grant"] = "1"
    if allow_downgrade:
        params["downgrade"] = "1"
    url = f"{_base_url()}/device/{_device_id(device)}/install"
    headers = {**_headers(), "Content-Type": "application/vnd.android.package-archive",
               "Content-Length": str(os.path.getsize(apk_path))}
    # Streamed from disk: APKs can be hundreds of MB.
    with open(apk_path, "rb") as f, httpx.Client(timeout=max(_timeout(), 300)) as client:
        try:
            resp = client.post(url, params=params, headers=headers, content=f)
        except httpx.TransportError as e:
            raise ToolError(
                f"could not reach the ERIUS PHONE API at {_base_url()} ({type(e).__name__}: {e}) — "
                "check ERIUS_PHONE_API_URL"
            ) from e
    # 422 = adb ran but the install failed; its body carries ok=false + the adb
    # error, which is the useful result. Anything else >= 400 (auth, unknown
    # device, not an APK, server error) is a real failure.
    if resp.status_code >= 400 and resp.status_code != 422:
        raise ToolError(f"install failed: {_error_text(resp)}")
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def main() -> None:
    """Console-script entry point (`erius-phone-mcp`): run over stdio."""
    # Warn on stderr (stdout is the MCP channel) but still start: MCP clients
    # tend to hide startup crashes, while the same message returned from a
    # tool call reaches the agent and the user.
    if not _env("ERIUS_PHONE_API_KEY"):
        print("erius-phone-mcp: warning: ERIUS_PHONE_API_KEY is not set; every tool call will fail "
              "until it is set in your MCP client's `env` block", file=sys.stderr)
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
