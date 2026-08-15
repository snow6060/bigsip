"""
bridge.py — standalone clipboard watcher for browser-based AI chats.

Run this alongside the main gateway (python -m app.main <file>).
Watches your clipboard for BIGSIP_SCHEMA: or BIGSIP_QUERY: <sql>,
runs the matching request against the local gateway, and replaces
your clipboard with the JSON result — ready to paste back into chat.
"""

import time
import json
import requests
import pyperclip

GATEWAY_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SECONDS = 0.5

SCHEMA_MARKER = "BIGSIP_SCHEMA:"
QUERY_MARKER = "BIGSIP_QUERY:"

HEARTBEAT_PATH = "bridge_heartbeat.txt"


def write_heartbeat():
    with open(HEARTBEAT_PATH, "w") as f:
        f.write(str(time.time()))


def handle_schema_request() -> str:
    response = requests.get(f"{GATEWAY_URL}/schema")
    response.raise_for_status()
    return json.dumps(response.json(), indent=2)


def handle_query_request(sql: str) -> str:
    response = requests.post(
        f"{GATEWAY_URL}/query",
        json={"sql": sql},
    )
    if response.status_code != 200:
        # Surface the gateway's error message (e.g. "Only SELECT queries
        # are allowed") back to the clipboard, so the AI sees it and can
        # correct its own query.
        return json.dumps({"error": response.json().get("detail", "Unknown error")}, indent=2)

    return json.dumps(response.json(), indent=2)


def process_clipboard_text(text: str) -> str | None:
    """
    Checks clipboard text against known markers.
    Returns the JSON result string if it matched something, else None.
    """
    stripped = text.strip()

    if stripped.startswith(SCHEMA_MARKER):
        try:
            return handle_schema_request()
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Could not reach gateway: {e}"}, indent=2)

    if stripped.startswith(QUERY_MARKER):
        sql = stripped[len(QUERY_MARKER):].strip()
        try:
            return handle_query_request(sql)
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Could not reach gateway: {e}"}, indent=2)

    return None


def main():
    print("bigsip Clipboard Bridge running.")
    print(f"Watching clipboard every {POLL_INTERVAL_SECONDS}s for '{SCHEMA_MARKER}' or '{QUERY_MARKER}'...")
    print("Press Ctrl+C to stop.\n")

    last_seen = pyperclip.paste()

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        write_heartbeat()
        current = pyperclip.paste()

        if current == last_seen:
            continue

        last_seen = current
        result = process_clipboard_text(current)

        if result is not None:
            pyperclip.copy(result)
            last_seen = result  # avoid re-triggering on our own output
            print("Processed a request — result copied to clipboard. Ready to paste.")


if __name__ == "__main__":
    main()