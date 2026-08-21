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

import threading
import time
import requests
import uvicorn
import webview
from pathlib import Path

from app.main import app, find_free_port

LOADING_PAGE = str(Path(__file__).resolve().parent.parent / "static" / "loading.html")
ICON_PATH = str(Path(__file__).resolve().parent.parent / "static" / "logo.ico")

# The splash is a deliberate, polished beat — not just a stopgap for
# server startup. It's shown for at least this long regardless of how
# fast uvicorn actually comes up, so a fast local start doesn't produce
# a flash the user barely registers. If the server takes LONGER than
# this, the swap simply waits for it — loading.html's "Starting up..."
# animation is indefinite by design, so it holds up fine either way.
MIN_SPLASH_SECONDS = 10.5


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


def main():
    port = find_free_port()

    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    window = webview.create_window(
        "bigsip",
        LOADING_PAGE,
        width=1000,
        height=800,
    )

    # webview.start()'s func/args run in a thread pywebview manages
    # internally, once the window exists — this call itself is what
    # blocks the main thread with the native window loop.
    webview.start(wait_for_server_and_swap, (window, port), icon=ICON_PATH)


if __name__ == "__main__":
    main()