"""
mcp_files.py — reads/writes the list of file paths that mcp_server.py
should have loaded into its DataEngine.

Exists because desktop.py's FastAPI process and mcp_server.py run as
two completely separate OS processes (mcp_server.py is launched by
Claude Desktop, not by us) — they don't share memory, so "the UI's
file picker" and "MCP's DataEngine" can only communicate through a
shared file on disk, same pattern as the port/heartbeat files.
"""

import json
from pathlib import Path

from app.paths import MCP_FILES_PATH


def read_mcp_files() -> list[str]:
    """
    Returns the list of file paths currently recorded, or an empty
    list if the file doesn't exist yet or is unreadable/corrupt —
    treated the same as "no files chosen yet" rather than an error,
    since this is read on every MCP tool call and shouldn't crash a
    query over a transient/missing file.
    """
    if not MCP_FILES_PATH.is_file():
        return []

    try:
        data = json.loads(MCP_FILES_PATH.read_text(encoding="utf-8"))
        return data.get("files", [])
    except (json.JSONDecodeError, OSError):
        return []


def write_mcp_files(paths: list[str]) -> None:
    """
    Overwrites the recorded file list with 'paths' — this is a full
    replace, not an append. Called by desktop.py's set_mcp_files(),
    itself called after the native file dialog returns a fresh
    selection, so "replace" matches "here's what should be loaded now"
    rather than "add these to whatever was there before."
    """
    MCP_FILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    MCP_FILES_PATH.write_text(json.dumps({"files": paths}, indent=2), encoding="utf-8")