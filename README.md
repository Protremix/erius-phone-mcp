# erius-phone-mcp

[![Erius Phone Mcp on AI Agents Listing](https://aiagentslisting.com/erius-phone-mcp-2/badge.svg?claim=908a95a9e43844298d2012188cd96279)](https://aiagentslisting.com/mcp/erius-phone-mcp-2)

<!-- mcp-name: io.github.Protremix/erius-phone-mcp -->

An [MCP](https://modelcontextprotocol.io) server that turns your
[ERIUS PHONE](https://eriusphone.com) device into native tools for Claude Code,
Claude Desktop, Cursor, or any other MCP client. An ERIUS PHONE device is a real
Android phone or tablet dedicated to your agent. Once this server is connected,
your agent can:

- list its devices
- read the screen as an accessibility tree or a screenshot
- tap, long-press, type, swipe and scroll
- launch and stop apps, open URLs and send intents
- install and uninstall APKs
- pull crash logs

The agent drives the device directly. You don't write any glue code.

> **Early access:** this package is pre-1.0 (`0.2.0`). Tool names and
> arguments may still change before 1.0.

## Requirements

- Python 3.10+
- An ERIUS PHONE **API key**. Sign up at <https://eriusphone.com>; see
  "Getting an API key" below.

## Install

**Option A: `uvx`** (no install step). If you have
[uv](https://docs.astral.sh/uv/), your MCP client can launch the server with
`uvx erius-phone-mcp`. uv fetches the package and keeps it in its own
environment. The client configs below show this form.

**Option B: `pip`**, into its own virtual environment so its dependencies
don't clash with your other Python projects:

```bash
python3 -m venv ~/.venvs/erius-phone-mcp
~/.venvs/erius-phone-mcp/bin/pip install erius-phone-mcp
```

This installs an `erius-phone-mcp` command at
`~/.venvs/erius-phone-mcp/bin/erius-phone-mcp`. Use that **absolute path** as
the `command` in your client config: GUI apps such as Claude Desktop and Cursor
usually don't see your venv's `PATH`. `python -m erius_phone_mcp` does the same
thing as running the command.

## Configuration

The server is configured entirely through environment variables:

| Variable | Required | What it is |
|---|---|---|
| `ERIUS_PHONE_API_KEY` | **yes** | Your ERIUS PHONE API key. Every request is authenticated with it and scoped to your account. |
| `ERIUS_PHONE_DEFAULT_DEVICE` | no | The device id to use when a tool call doesn't name one (e.g. `vanilla`). Without it, the agent passes `device` on each call; `list_devices` shows the ids. |
| `ERIUS_PHONE_API_URL` | no | API base URL. Default `https://api.eriusphone.com`; only set it if we gave you a different one. |
| `ERIUS_PHONE_TIMEOUT` | no | HTTP timeout per request, in seconds. Default `30`. |

### Getting an API key

Request access at <https://eriusphone.com>. During early access the ERIUS
PHONE team sets up each account by hand. You'll receive your API key and
device id(s) directly from us. If you signed up and haven't heard back, email
info@eriusphone.com. The same key signs you in to the dashboard at
<https://eriusphone.com/dashboard/>, which shows your devices live.

Treat the key like a password: anyone who has it can control your device.

> **Important:** MCP clients start this server as a subprocess, and they
> generally do **not** pass along variables you `export` in your shell. Put
> the variables in the client's `env` block, as shown below.

## Add it to your MCP client

In every example, replace the key and device id with your own. If you
installed with pip instead of using `uvx`, replace `"command": "uvx", "args":
["erius-phone-mcp"]` with `"command": "/home/you/.venvs/erius-phone-mcp/bin/erius-phone-mcp"`.

### Claude Code

```bash
claude mcp add erius-phone \
  -e ERIUS_PHONE_API_KEY=your-api-key \
  -e ERIUS_PHONE_DEFAULT_DEVICE=your-device-id \
  -- uvx erius-phone-mcp
```

Add `-s user` to make the server available in all your projects, or
`-s project` to write it to a shared `.mcp.json`. Don't commit your key to a
shared `.mcp.json`. Claude Code expands `${VAR}` references in that file, so
you can keep the key in an environment variable instead:

```json
{
  "mcpServers": {
    "erius-phone": {
      "command": "uvx",
      "args": ["erius-phone-mcp"],
      "env": {
        "ERIUS_PHONE_API_KEY": "${ERIUS_PHONE_API_KEY}",
        "ERIUS_PHONE_DEFAULT_DEVICE": "your-device-id"
      }
    }
  }
}
```

Run `/mcp` inside Claude Code to check that `erius-phone` is connected.

### Claude Desktop

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config). On
macOS it's in `~/Library/Application Support/Claude/`; on Windows it's in
`%APPDATA%\Claude\`.

```json
{
  "mcpServers": {
    "erius-phone": {
      "command": "uvx",
      "args": ["erius-phone-mcp"],
      "env": {
        "ERIUS_PHONE_API_KEY": "your-api-key",
        "ERIUS_PHONE_DEFAULT_DEVICE": "your-device-id"
      }
    }
  }
}
```

If Claude Desktop can't find `uvx`, put its absolute path in `command`
(`which uvx`). Fully quit and reopen Claude Desktop after editing.

### Cursor

Put the same `mcpServers` block in `~/.cursor/mcp.json` to use it in all
projects, or in `.cursor/mcp.json` for one project. Then enable `erius-phone`
under Cursor Settings → MCP.

### Any other MCP client

The server speaks MCP over **stdio**. Point your client at `uvx
erius-phone-mcp`, or at the `erius-phone-mcp` executable, and pass the
environment variables above.

## Tools

Every tool that acts on a device takes an optional `device` argument. If you
leave it out, the tool uses `ERIUS_PHONE_DEFAULT_DEVICE`.

**Account and devices**

| Tool | Description |
|---|---|
| `whoami` | Which account and key this server is using, and the device ids it can access. A quick way to check the key works. |
| `list_devices` | Every device your key can access, with live status (booted, Android version, screen size). |
| `get_device` | Full status of one device, including the app currently in the foreground. |

**Seeing the screen**

| Tool | Description |
|---|---|
| `snapshot` | Accessibility-tree snapshot of the current screen: every visible element with its text, role and a `ref` you can pass to tap/type/scroll. Refs reset on every snapshot. |
| `screenshot` | The screen as MCP image content, so the model sees it directly. Default: JPEG, longest side 1024 px (tens of KB). `format`, `quality`, `max_side` and `scale` change that; `format="png", max_side=null` gives the full-size PNG (about 3 MB on a phone). A text line gives the image and screen sizes. |
| `foreground` | Just the foreground app (package, activity) and whether a crash dialog is showing. |
| `wait_for_text` | Wait until some text appears on screen, up to `timeout_ms` (max 120000). Returns the snapshot it saw. |

**Acting on the screen**

| Tool | Description |
|---|---|
| `tap` | Tap by `ref`, by visible `text`/`content_desc`, or at raw `x`,`y` pixels. |
| `long_press` | Long-press by `ref`, by `text`/`content_desc`, or at `x`,`y` (optional hold time `ms`). |
| `type_text` | Type into a field. Can tap a `ref`/`text_target` first, `clear` the field, and press Enter after. |
| `press_key` | back, home, enter, delete, tab, escape, up, down, left, right, space, power, volup, voldown, recent, menu, wakeup, or a numeric keycode. |
| `swipe` | Swipe between two points in device pixels. |
| `scroll` | Scroll a container up/down/left/right. Pass the `ref` of the ScrollView/List itself, not of a row inside it. |

**Apps**

| Tool | Description |
|---|---|
| `launch_app` | Launch an installed app by package name (e.g. `com.android.settings`). |
| `open_url` | Open an http/https/market URL, optionally in a specific app. |
| `send_intent` | Start an activity with any intent action, e.g. `android.settings.WIFI_SETTINGS`, with optional data, package, component and extras. |
| `stop_app` | Force-stop an app. |
| `list_apps` | Installed apps; `third_party_only=True` for user-installed ones only. |
| `install_apk` | Upload and install an APK from a file on the machine running this server. Returns package name, version, and whether the install succeeded. |
| `uninstall_app` | Uninstall an app by package name. |
| `get_crash_log` | The device's crash log buffer (`logcat -b crash`). Use it after an app crashes to see the real stack trace. |

## Quick example

Once the server is connected, ask your agent in plain language, e.g.
*"List my ERIUS devices, go to the home screen, and open Contacts."* Here's what
happens under the hood. The outputs below are real, lightly trimmed.

**1. Find your device.** The agent calls `list_devices`:

```json
{"devices": [
  {"id": "vanilla", "description": "redroid Android 13, no Google services", "state": "device",
   "bootCompleted": true, "android": "13", "sdk": 33, "screen": {"width": 720, "height": 1280}},
  {"id": "tablet1", "form": "tablet", "description": "redroid Android 13 (vanilla, tablet)", "state": "device",
   "bootCompleted": true, "android": "13", "sdk": 33, "screen": {"width": 1600, "height": 2560}}
]}
```

**2. Go home and look at the screen.** `press_key(key="home", device="vanilla")`
returns `{"ok": true}`, then `snapshot(device="vanilla")` returns the
foreground app plus this tree:

```
- Group
  - ScrollView [ref=1]
    - Group
      - AppWidgetHostView (Search)
        ...
      - Text [ref=4] "Gallery" (Gallery)
  - View (Home)
  - Group
    - Text [ref=5] "Contacts" (Contacts)
    - Text [ref=6] "WebView Browser Tester" (WebView Browser Tester)
    - Text [ref=7] "Camera" (Camera)
```

**3. Tap something.** `tap(device="vanilla", ref="5")`, `tap(device="vanilla",
text="Contacts")` and `tap(device="vanilla", x=102, y=1116)` all open Contacts
and return `{"ok": true}`. After any action, take a fresh `snapshot`, because
refs are only valid until the next one.

**4. Check the result.** `foreground(device="vanilla")` now reports the
Contacts app, and `screenshot(device="vanilla")` returns the screen as an
image your agent sees directly.

**Installing an APK** for QA works the same way:

```
install_apk(device="vanilla", apk_path="/path/to/app.apk")
→ {"ok": true, "package": "com.erius.dashtest", "versionName": "1.0", "label": "ERIUS Dash Test",
   "adbOutput": "Performing Streamed Install\nSuccess", "ms": 94, ...}
```

## Tips and limits

- **Errors are passed through.** If the API refuses an action, the tool call
  fails with the API's error code and message, e.g. `HTTP 404: SelectorNotFound
  ... nothing on screen matches {"text": "..."}` or `HTTP 422:
  no_launcher_activity`. The agent can read the message and adjust.
- **Typing needs a ready field.** Keystrokes sent while a field is still
  opening are lost. If tapping a field opens a new screen (as Android
  Settings' search does), tap it, wait with `snapshot`/`wait_for_text`, then
  call `type_text` without a target. Check the result with `snapshot`.
- **ASCII-only typing.** `type_text` supports printable ASCII only (an adb
  limitation): no emoji, accented characters or non-Latin scripts.
- **Scroll by container.** `scroll` needs the ref of the scrollable container
  (a `ScrollView`/`List` line in the snapshot). If the container has no ref,
  use `swipe`.
- **Screenshots cost context.** The default screenshot is a JPEG with its
  longest side at 1024 px (tens of KB). A full-size PNG of a phone
  (1440×3120) is about 3 MB, more than many MCP clients accept in one tool
  result. Prefer `snapshot` (text, much smaller) and take screenshots only
  when you need pixels.
- **Coordinates from a scaled screenshot.** `x`,`y` are device pixels unless
  you pass `image_width` and `image_height` (the size of the screenshot you
  read them from) to `tap`, `long_press` or `swipe`.
- **`install_apk` reads a local file.** The path is on the machine running
  `erius-phone-mcp`, not on the phone. The APK is streamed from disk and
  uploaded in full on each call.
- **One server process = one API key.** To use several accounts, add several
  server entries with different names and keys.
- **Rate limits.** The API allows about 30 requests per second per IP and
  queues at most 8 requests per device; beyond that you get HTTP 429.

## Troubleshooting

- `ERIUS_PHONE_API_KEY is not set`: the variable didn't reach the server
  process. Put it in the client's `env` block, not just your shell. The server
  also prints a warning about this on stderr at startup, which shows up in your
  client's MCP logs.
- `no device id given and ERIUS_PHONE_DEFAULT_DEVICE is not set`: pass
  `device=` in the tool call or set `ERIUS_PHONE_DEFAULT_DEVICE`. `list_devices`
  shows your ids.
- `HTTP 401`: the key is wrong or revoked. `HTTP 403`: the device id doesn't
  exist or isn't on your account. Run `whoami` to see which devices your key
  can use.
- `HTTP 503 device_offline`: the device is restarting. Retry shortly.
- `could not reach the ERIUS PHONE API at ...`: the URL is wrong, or the API
  is unreachable from your machine. Check `ERIUS_PHONE_API_URL`, and raise
  `ERIUS_PHONE_TIMEOUT` if you're on a slow link.

## License

MIT. The full license text is in the `LICENSE` file shipped with the package.
