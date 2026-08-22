"""
mcp_server.py — exposes the DataEngine as MCP tools, so Claude Desktop
can call schema/query equivalents natively, without HTTP.

Unlike main.py, this doesn't take command-line file arguments —
Claude Desktop launches this script directly. Which files are loaded
is controlled by mcp_files.json (see app/mcp_files.py), written by
desktop.py's UI whenever the user picks files in MCP mode. This
script checks that file for changes before every tool call, so a
file picked in the UI becomes available to Claude Desktop on the very
next question asked — no restart needed for that part (restarting
Claude Desktop is only required for the one-time config/connection
setup itself, handled separately by app/mcp_config.py).
"""

import os
import threading
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from app.engine import DataEngine
from app.paths import MCP_HEARTBEAT_FILE_PATH, MCP_FILES_PATH
from app.mcp_files import read_mcp_files

mcp = FastMCP("bigsip")
engine = DataEngine()

_loaded_paths: set[str] = set()
_last_seen_mtime: float | None = None


def _sync_files_if_changed():
    """
    Checks mcp_files.json's modification time; if it's changed since
    the last check, loads any newly-listed files that aren't already
    loaded. Cheap no-op (a single stat() call) when nothing's changed,
    so calling this before every tool call has negligible overhead.

    Deliberately never REMOVES already-loaded tables if a file drops
    off the list — DuckDB's :memory: engine has no clean "unload one
    table" operation here, and silently dropping data mid-session
    could break a query the user's already relying on. Removal would
    need its own deliberate design, not a side effect of this sync.
    """
    global _last_seen_mtime

    try:
        mtime = MCP_FILES_PATH.stat().st_mtime
    except OSError:
        return  # no file yet — nothing chosen in the UI so far

    if mtime == _last_seen_mtime:
        return
    _last_seen_mtime = mtime

    for file_path in read_mcp_files():
        if file_path in _loaded_paths:
            continue

        ext = Path(file_path).suffix.lower()
        try:
            if ext == ".csv":
                engine.load_csv(file_path)
            elif ext == ".xlsx":
                engine.load_xlsx(file_path)
            else:
                print(f"mcp_server: skipping unsupported file type: {file_path}")
                continue
        except ValueError as e:
            # Table name collision (e.g. file already loaded under a
            # different path, or two files sharing a sanitized name) —
            # log and skip rather than crash tool calls over one bad
            # file in the list.
            print(f"mcp_server: could not load '{file_path}': {e}")
            continue

        _loaded_paths.add(file_path)


_HEARTBEAT_INTERVAL_SECONDS = 1.0


def _write_heartbeat_loop():
    """
    Writes a timestamp to MCP_HEARTBEAT_FILE_PATH every
    _HEARTBEAT_INTERVAL_SECONDS, for as long as this process is alive.
    Lets bigsip's own dashboard distinguish "MCP is configured in
    Claude Desktop's config" from "MCP is actually running right now."
    Runs as a daemon thread so it never blocks mcp.run() and dies
    automatically when the process exits.
    """
    while True:
        try:
            MCP_HEARTBEAT_FILE_PATH.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass
        time.sleep(_HEARTBEAT_INTERVAL_SECONDS)


@mcp.tool()
def get_schema() -> dict:
    """
    Returns the structure of all loaded tables: column names, types,
    and a few sample rows. Call this first to understand what data
    is available before writing a query.
    """
    _sync_files_if_changed()
    return engine.get_schema()


@mcp.tool()
def run_query(sql: str) -> dict:
    """
    Runs a read-only SQL SELECT query against the loaded data and
    returns the results. Only SELECT statements are allowed. Results
    are capped at 1000 rows — check the 'truncated' field in the
    response to see if more rows exist than were returned.
    """
    _sync_files_if_changed()
    return engine.run_query(sql)


if __name__ == "__main__":
    heartbeat_thread = threading.Thread(target=_write_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    _sync_files_if_changed()  # pick up any files already chosen before this launch
    mcp.run()