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

import sys
from pathlib import Path
import platformdirs

_APP_NAME = "bigsip"


def resource_path(*parts: str) -> Path:
    """
    Resolves a path to a bundled resource (static/docs files shipped
    WITH the app, not runtime-generated coordination files — see
    get_app_data_dir() for those).

    Running from source: walks up from this file to the repo root.

    Running as a frozen PyInstaller build: uses sys._MEIPASS, which
    PyInstaller sets specifically for this purpose — it always points
    to wherever bundled 'datas' actually landed, whether that's a
    --onefile temp extraction folder or a --onedir build's internal
    data folder (PyInstaller 6.0+ moved onedir's bundled files into an
    '_internal' subfolder rather than next to the .exe directly — using
    sys._MEIPASS avoids hardcoding either layout).
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def get_app_data_dir() -> Path:
    data_dir = Path(platformdirs.user_data_dir(_APP_NAME))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


PORT_FILE_PATH = get_app_data_dir() / "bigsip_port.txt"
HEARTBEAT_FILE_PATH = get_app_data_dir() / "bridge_heartbeat.txt"
MCP_HEARTBEAT_FILE_PATH = get_app_data_dir() / "mcp_heartbeat.txt"
MCP_FILES_PATH = get_app_data_dir() / "mcp_files.json"
LOAD_PROGRESS_PATH = get_app_data_dir() / "load_progress.json"
LOAD_TEMP_DIR = get_app_data_dir() / "load_temp"