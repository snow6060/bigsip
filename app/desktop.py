"""
desktop.py — pywebview entrypoint for the packaged desktop app.

Launches uvicorn (serving the same FastAPI app as main.py) in a
background thread, then hands control of the main thread over to
pywebview's window loop. pywebview requires owning the main thread
(a hard requirement on macOS/Cocoa, and the recommended pattern
everywhere else) — so unlike main.py, THIS script's main thread is
the window, not the server.

Run with: python -m app.desktop
No file arguments — files are loaded after the window opens, via the
existing /load endpoint (a native file dialog replaces the current
prompt()-based picker in a later step of this same phase).
"""

import json
import os
import sys
import threading
import time
import requests
import uvicorn
import webview
import pyperclip
from pathlib import Path

from app.main import app, find_free_port
from app.mcp_config import find_claude_config_path, get_mcp_status, write_mcp_config
from app.paths import MCP_HEARTBEAT_FILE_PATH, PORT_FILE_PATH, resource_path
from app.mcp_files import write_mcp_files
from bridge import process_clipboard_text, write_heartbeat, POLL_INTERVAL_SECONDS


LOADING_PAGE = str(resource_path("static", "loading.html"))
ICON_PATH = str(resource_path("static", "logo.ico"))

# The splash is a deliberate, polished beat — not just a stopgap for
# server startup. It's shown for at least this long regardless of how
# fast uvicorn actually comes up, so a fast local start doesn't produce
# a flash the user barely registers. If the server takes LONGER than
# this, the swap simply waits for it — loading.html's "Starting up..."
# animation is indefinite by design, so it holds up fine either way.
MIN_SPLASH_SECONDS = 10.5

# The MCP heartbeat is written roughly every 1s (see mcp_server.py) —
# this allows some slack for scheduling jitter before treating it as
# stale rather than requiring a sub-second-perfect match.
_MCP_HEARTBEAT_FRESHNESS_SECONDS = 3

# Set once in main() once the real port is known — start_bridge() needs
# this to build the correct gateway URL for process_clipboard_text().
_gateway_url: str | None = None
_bridge_stop_event = threading.Event()
_bridge_thread: threading.Thread | None = None


def run_server(port: int):
    """
    Runs uvicorn in this thread. uvicorn.Server.run() blocks, which is
    exactly what we want — this thread's only job is being the server,
    for as long as the process lives (it's a daemon thread, so it dies
    automatically when the main thread/window closes).
    """
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def wait_for_server_and_swap(window, port: int):
    """
    Passed to webview.start() as the function to run once the window
    exists. Polls /status (not /schema — /status is always a valid 200
    even with zero tables loaded, which is exactly our startup state)
    until the gateway answers, then tops off the remaining time to hit
    MIN_SPLASH_SECONDS before swapping the window's content over from
    the static loading page to the live dashboard. These are two
    independent conditions — "server ready" and "minimum time elapsed"
    — and both must be true before the swap happens.
    """
    gateway_url = f"http://127.0.0.1:{port}"
    start_time = time.monotonic()

    while True:
        try:
            response = requests.get(f"{gateway_url}/status", timeout=0.5)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass  # server not up yet — keep polling
        time.sleep(0.2)

    elapsed = time.monotonic() - start_time
    remaining = MIN_SPLASH_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)

    window.load_url(f"{gateway_url}/ui")


def check_mcp_status() -> dict:
    """
    Exposed to JS as pywebview.api.check_mcp_status(). Returns
    {"status": "..."} where status is one of:
    - "not_configured" — no config file, or no correct bigsip entry
      in it (mcp_config.get_mcp_status()'s "not_found" and
      "not_configured" both collapse into this one UI-facing state)
    - "configured"      — a correct entry exists, but the heartbeat
      is missing or stale — Claude Desktop isn't currently running
      the server as a subprocess right now
    - "online"          — correct entry exists AND the heartbeat is
      fresh — proof Claude Desktop has it running right now
    """
    config_path = find_claude_config_path()
    config_status = get_mcp_status(config_path)  # "not_found" / "not_configured" / "configured"

    if config_status != "configured":
        return {"status": "not_configured"}

    try:
        heartbeat_age = time.time() - MCP_HEARTBEAT_FILE_PATH.stat().st_mtime
        if heartbeat_age < _MCP_HEARTBEAT_FRESHNESS_SECONDS:
            return {"status": "online"}
    except OSError:
        pass  # heartbeat file doesn't exist yet — server has never run

    return {"status": "configured"}


def setup_mcp(manual_config_path: str | None = None) -> dict:
    """
    Exposed to JS as pywebview.api.setup_mcp(). Writes/updates the
    bigsip entry in claude_desktop_config.json.

    If manual_config_path is provided (the user pasted a path
    themselves via the "?" fallback), that's used directly instead of
    auto-detection — covers the case where find_claude_config_path()
    can't locate a non-standard install.

    Returns a plain dict rather than raising, since this is called
    directly from JS via pywebview and needs a JSON-serializable
    result either way — {"success": True} or
    {"success": False, "error": "..."}.
    """
    if manual_config_path:
        config_path = Path(manual_config_path)
    else:
        config_path = find_claude_config_path()

    if config_path is None:
        return {
            "success": False,
            "error": (
                "Could not find claude_desktop_config.json automatically. "
                "Please paste the path manually."
            ),
        }

    try:
        write_mcp_config(config_path)
    except (OSError, json.JSONDecodeError) as e:
        return {"success": False, "error": str(e)}

    return {"success": True}


def set_mcp_files(paths: list[str]) -> dict:
    """
    Exposed to JS as pywebview.api.set_mcp_files(paths). Called after
    the native file dialog returns a selection in MCP mode — writes
    the chosen paths to mcp_files.json, which mcp_server.py picks up
    on its next tool call (no restart needed for this part).
    """
    try:
        write_mcp_files(paths)
    except OSError as e:
        return {"success": False, "error": str(e)}

    return {"success": True}


def restart_app():
    """
    Exposed to JS as pywebview.api.restart_app(). Relaunches the
    entire process from scratch rather than trying to reset state
    piecemeal while everything's still running — DataEngine is
    :memory: only, so a new process is a genuinely clean slate with
    no special-case cleanup logic needed.
    """
    python = sys.executable
    os.execv(python, [python, "-m", "app.desktop"])


def select_files() -> list[str]:
    """
    Exposed to JS as pywebview.api.select_files(). Opens a native
    multi-select file dialog and returns the chosen absolute paths —
    no manual path-typing, unlike the old prompt()-based picker.
    Returns an empty list if the user cancels.
    """
    file_types = ('Data Files (*.csv;*.xlsx)', 'All files (*.*)')
    result = webview.windows[0].create_file_dialog(
        webview.OPEN_DIALOG, allow_multiple=True, file_types=file_types
    )
    return list(result) if result else []


def _bridge_loop():
    """
    Runs on its own daemon thread once start_bridge() is called.
    Mirrors bridge.py's main() polling loop exactly, but checks
    _bridge_stop_event each cycle so stop_bridge() can end it cleanly
    (e.g. when the user switches away from Browser-Based Agents mode)
    instead of only ever stopping when the whole process exits.
    """
    last_seen = pyperclip.paste()

    while not _bridge_stop_event.is_set():
        time.sleep(POLL_INTERVAL_SECONDS)
        write_heartbeat()
        current = pyperclip.paste()

        if current == last_seen:
            continue

        last_seen = current
        result = process_clipboard_text(current, _gateway_url)

        if result is not None:
            pyperclip.copy(result)
            last_seen = result  # avoid re-triggering on our own output


def start_bridge() -> dict:
    """
    Exposed to JS as pywebview.api.start_bridge(). Starts the
    clipboard-watching loop as a daemon thread, using bridge.py's
    real logic (process_clipboard_text, write_heartbeat) rather than
    a duplicate copy. Safe to call more than once — a no-op if the
    bridge is already running.
    """
    global _bridge_thread

    if _bridge_thread is not None and _bridge_thread.is_alive():
        return {"success": True}  # already running

    _bridge_stop_event.clear()
    _bridge_thread = threading.Thread(target=_bridge_loop, daemon=True)
    _bridge_thread.start()
    return {"success": True}


def stop_bridge() -> dict:
    """
    Exposed to JS as pywebview.api.stop_bridge(). Signals the
    clipboard-watching thread to stop after its current sleep cycle
    (at most POLL_INTERVAL_SECONDS delay, not instant). Safe to call
    even if the bridge isn't running.
    """
    _bridge_stop_event.set()
    return {"success": True}


def main():
    global _gateway_url

    port = find_free_port()
    PORT_FILE_PATH.write_text(str(port), encoding="utf-8")
    _gateway_url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    window = webview.create_window(
        "bigsip",
        LOADING_PAGE,
        width=1000,
        height=800,
    )

    # Registers check_mcp_status/setup_mcp/set_mcp_files/restart_app as callable
    # from JS via pywebview.api. Must happen after create_window() (needs a window
    # to attach to) and before webview.start() (which blocks until the window closes).
    window.expose(
        check_mcp_status,
        setup_mcp,
        set_mcp_files,
        restart_app,
        select_files,
        start_bridge,
        stop_bridge,
    )

    # webview.start()'s func/args run in a thread pywebview manages
    # internally, once the window exists — this call itself is what
    # blocks the main thread with the native window loop.
    
    webview.start(wait_for_server_and_swap, (window, port), icon=ICON_PATH)


if __name__ == "__main__":
    main()