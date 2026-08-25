# bigsip.spec — PyInstaller build recipe for the packaged desktop app.
#
# Build with:
#   pyinstaller bigsip.spec
#
# One-folder build (not one-file) — easier to inspect/debug what's
# actually bundled on a first packaging attempt. dist/bigsip/ is the
# output; bigsip.exe inside it is what a user would run.

import sys
from pathlib import Path

block_cipher = None

# ── Static assets bigsip reads from disk at runtime, not import time ──
# static/ — the whole UI (html/css/js/images), served by FastAPI's
# StaticFiles mount and read directly by desktop.py for the splash
# page and icon.
# docs/system-prompt.md — read live by main.py's /prompt endpoint on
# every request. Easy to forget since it's not imported as code.
datas = [
    ("static", "static"),
    ("docs/system-prompt.md", "docs"),
]

# ── Hidden imports ──
# PyInstaller's static analysis can miss modules that are imported
# dynamically at runtime rather than at the top of a file. Starting
# set based on known dynamic-loading behavior in our three riskiest
# dependencies (uvicorn, duckdb, pywebview) — expect to add more here
# after the first test run surfaces what's actually missing.
hidden_imports = [
    # uvicorn's protocol/loop implementations are selected dynamically
    # at startup based on what's installed, not imported directly by
    # our code.
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",

    # duckdb's Python bindings wrap a compiled native extension —
    # usually fine, but worth an explicit hint.
    "duckdb",

    # pywebview picks its actual rendering backend at runtime based on
    # what's available on the machine. On Windows this is normally
    # Edge WebView2 (edgechromium); mshtml is the legacy IE-based
    # fallback pywebview can also fall back to.
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.mshtml",

    # openpyxl/pandas — used by xlsx_worker.py, which runs in a
    # SEPARATE PROCESS via ProcessPoolExecutor. That subprocess is
    # spawned by re-invoking the frozen .exe itself, not a normal
    # Python import — worth being explicit here too.
    "openpyxl",
    "pandas",
    "pyarrow",
]

a = Analysis(
    ["app/desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bigsip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no terminal window — this is a GUI app
    icon="static/logo.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="bigsip",
)