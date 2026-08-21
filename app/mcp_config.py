"""
mcp_config.py — finds, reads, and writes bigsip's entry in Claude
Desktop's claude_desktop_config.json.

Knows nothing about the UI or about MCP heartbeat/online status —
its only job is: locate the config file, check whether bigsip's
entry in it is present and correct, and write a correct one if asked.
"""

import glob
import json
import os
import sys
from pathlib import Path

# The bigsip repo root — two levels up from this file (app/mcp_config.py
# -> app/ -> repo root). Used to build the absolute path to mcp_server.py
# and to set PYTHONPATH, matching the setup documented in Test 3
# (docs/case-study.md) that got MCP working in the first place.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MCP_SERVER_SCRIPT = _REPO_ROOT / "app" / "mcp_server.py"

_SERVER_NAME = "bigsip"


def find_claude_config_path() -> Path | None:
    """
    Searches the known locations for claude_desktop_config.json on
    Windows. Returns the first match found, or None if neither exists.

    Two known layouts (both encountered during Test 3):
    - A plain %APPDATA%\\Claude\\claude_desktop_config.json
    - A packaged-app path under %LOCALAPPDATA%\\Packages\\Claude_<suffix>\\...
      — the <suffix> isn't predictable, so this uses a glob instead of
      a hardcoded path.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        plain_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
        if plain_path.is_file():
            return plain_path

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        pattern = str(
            Path(local_appdata) / "Packages" / "Claude_*" / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
        )
        matches = glob.glob(pattern)
        if matches:
            return Path(matches[0])

    return None


def _expected_mcp_entry() -> dict:
    """
    Builds the mcpServers entry bigsip *should* have, based on the
    Python interpreter currently running this code (sys.executable —
    which is the venv's python.exe when running inside the activated
    venv) and this repo's actual on-disk location.

    Uses an explicit python.exe + script-path command (not `-m
    app.mcp_server`) with PYTHONPATH set via env, per the Test 3
    finding that a launched MCP server's working directory should be
    treated as undefined — `-m` plus relying on cwd proved unreliable.
    """
    return {
        "command": sys.executable,
        "args": [str(_MCP_SERVER_SCRIPT)],
        "env": {
            "PYTHONPATH": str(_REPO_ROOT),
        },
    }


def get_mcp_status(config_path: Path | None) -> str:
    """
    Returns one of:
    - "not_found"      — no config file exists at all
    - "not_configured" — config file exists, but has no bigsip entry,
                          or the entry present doesn't match what's
                          expected (stale path, wrong interpreter, etc.)
    - "configured"     — a correct bigsip entry is present

    Does NOT check whether Claude Desktop currently has the server
    running — that's a separate "online" check, layered in once
    mcp_server.py's heartbeat file exists (next step).
    """
    if config_path is None or not config_path.is_file():
        return "not_found"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt or unreadable config is treated the same as "not
        # configured" — write_mcp_config will need to handle this
        # gracefully too, rather than assume the file is always valid.
        return "not_configured"

    servers = data.get("mcpServers", {})
    existing_entry = servers.get(_SERVER_NAME)

    if existing_entry == _expected_mcp_entry():
        return "configured"

    return "not_configured"


def write_mcp_config(config_path: Path) -> None:
    """
    Merges a correct bigsip entry into the config file at config_path,
    preserving any other keys/servers already present. If the file
    doesn't exist yet, creates it with just the bigsip entry.

    Raises OSError if the file can't be written (e.g. permissions),
    or json.JSONDecodeError if an existing file is present but corrupt
    — both are left for the caller to handle and surface to the user,
    rather than silently swallowed here.
    """
    if config_path.is_file():
        data = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        data = {}
        config_path.parent.mkdir(parents=True, exist_ok=True)

    data.setdefault("mcpServers", {})
    data["mcpServers"][_SERVER_NAME] = _expected_mcp_entry()

    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")