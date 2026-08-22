"""
paths.py — single source of truth for where bigsip's runtime
coordination files live (the port file main.py writes on startup,
and the heartbeat file bridge.py writes).

These used to live directly in the project folder, which works fine
for local dev but breaks for a packaged .exe (a packaged app generally
shouldn't/can't write next to its own executable — e.g. it might sit
in Program Files, which requires elevated permissions to write into).

platformdirs resolves the correct OS-specific app-data directory for
us (e.g. %LOCALAPPDATA%\\bigsip on Windows) instead of us hand-rolling
that per-OS logic.
"""

from pathlib import Path
import platformdirs

_APP_NAME = "bigsip"


def get_app_data_dir() -> Path:
    data_dir = Path(platformdirs.user_data_dir(_APP_NAME))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


PORT_FILE_PATH = get_app_data_dir() / "bigsip_port.txt"
HEARTBEAT_FILE_PATH = get_app_data_dir() / "bridge_heartbeat.txt"
MCP_HEARTBEAT_FILE_PATH = get_app_data_dir() / "mcp_heartbeat.txt"
MCP_FILES_PATH = get_app_data_dir() / "mcp_files.json"