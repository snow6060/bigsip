"""
main.py — the web layer. Defines HTTP endpoints and translates
HTTP requests into calls on the DataEngine.
"""

import sys
import json
import concurrent.futures
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from app.engine import DataEngine
import time
import os

app = FastAPI(title="bigsip gateway")
engine = DataEngine()

# Thread pool used to run queries with a best-effort timeout. DuckDB
# doesn't reliably support cancelling an in-progress query, so this
# stops us WAITING on a stuck query — it does not guarantee the query
# itself stops running in the background.
_query_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_QUERY_TIMEOUT_SECONDS = 15
_start_time = time.time()

class QueryRequest(BaseModel):
    sql: str

class LoadFileRequest(BaseModel):
    file_path: str
    table_name: str | None = None
    sheets: list[str] | None = None



@app.on_event("startup")
def load_data_on_startup():
    if len(sys.argv) < 2:
        raise RuntimeError(
            "Usage: python -m app.main <file1.csv|xlsx> [more files...]"
        )

    file_paths = sys.argv[1:]
    for file_path in file_paths:
        ext = Path(file_path).suffix.lower()

        try:
            if ext == ".csv":
                engine.load_csv(file_path)
                print(f"Loaded '{file_path}' into table '{engine.table_names[-1]}'.")
            elif ext == ".xlsx":
                before = set(engine.table_names)
                engine.load_xlsx(file_path)
                new_tables = [t for t in engine.table_names if t not in before]
                print(f"Loaded '{file_path}' into tables: {', '.join(new_tables)}")
            else:
                raise RuntimeError(f"Unsupported file type: '{file_path}'")
        except ValueError as e:
            # Catches table name collisions with a clean message instead
            # of a raw traceback crashing the whole startup.
            print(f"\nERROR loading '{file_path}': {e}")
            print("Startup aborted. Fix the conflicting file/table name and try again.\n")
            sys.exit(1)


@app.get("/schema")
def get_schema():
    try:
        return engine.get_schema()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/query")
def run_query(request: QueryRequest):
    try:
        future = _query_executor.submit(engine.run_query, request.sql)
        result = future.result(timeout=_QUERY_TIMEOUT_SECONDS)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except concurrent.futures.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=(
                f"Query did not complete within {_QUERY_TIMEOUT_SECONDS} seconds "
                f"and was abandoned. Note: the query may still be running in the "
                f"background — DuckDB does not guarantee cancellation."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query failed: {str(e)}")


STATIC_PROMPT_PATH = Path(__file__).parent.parent / "docs" / "system-prompt.md"


@app.get("/prompt", response_class=PlainTextResponse)
def get_prompt(context: str | None = None):
    try:
        static_rules = STATIC_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="docs/system-prompt.md not found — cannot generate prompt."
        )

    try:
        schema = engine.get_schema()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    schema_text = json.dumps(schema, indent=2)

    parts = [static_rules.strip()]

    if context:
        parts.append(f"\nADDITIONAL CONTEXT FROM THE USER:\n{context.strip()}")

    parts.append(f"\nCURRENT DATA SCHEMA (already loaded, no need to request BIGSIP_SCHEMA first):\n{schema_text}")

    return "\n\n".join(parts)


@app.post("/load")
def load_file(request: LoadFileRequest):
    """
    Loads a file into the already-running engine. Unlike startup-time
    loading (via command-line args), this lets the UI load files after
    the server is already running.
    """
    ext = Path(request.file_path).suffix.lower()

    try:
        if ext == ".csv":
            engine.load_csv(request.file_path, table_name=request.table_name)
            new_tables = [engine.table_names[-1]]
        elif ext == ".xlsx":
            before = set(engine.table_names)
            engine.load_xlsx(request.file_path, sheets=request.sheets)
            new_tables = [t for t in engine.table_names if t not in before]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: '{request.file_path}'"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load file: {str(e)}")

    return {"loaded_tables": new_tables}


@app.get("/status")
def get_status():
    """
    Returns basic runtime info for the UI's dashboard: which tables are
    loaded, how long the server's been running, and DuckDB's reported
    memory usage.
    """
    uptime_seconds = round(time.time() - _start_time, 1)

    try:
        result = engine.con.execute("SELECT * FROM pragma_database_size()")
        column_names = [desc[0] for desc in result.description]
        row = result.fetchone()
        db_size_info = dict(zip(column_names, row)) if row else {}

        memory_usage = {
            "memory_usage": db_size_info.get("memory_usage", "unknown"),
            "memory_limit": db_size_info.get("memory_limit", "unknown"),
        }
    except Exception:
        # Fail gracefully if the pragma's shape ever changes across
        # DuckDB versions, rather than breaking /status entirely.
        memory_usage = {"memory_usage": "unavailable", "memory_limit": "unavailable"}

    return {
        "tables_loaded": engine.table_names,
        "uptime_seconds": uptime_seconds,
        **memory_usage,
    }


HEARTBEAT_PATH = "bridge_heartbeat.txt"
_BRIDGE_HEARTBEAT_TIMEOUT = 3  # seconds


@app.get("/bridge-status")
def get_bridge_status():
    """
    Checks if the clipboard bridge is running by looking at the heartbeat
    file written by bridge.py. If the file exists and was modified within
    the last _BRIDGE_HEARTBEAT_TIMEOUT seconds, the bridge is considered
    active.
    """
    try:
        mtime = os.path.getmtime(HEARTBEAT_PATH)
        age = time.time() - mtime
        bridge_running = age < _BRIDGE_HEARTBEAT_TIMEOUT
    except OSError:
        bridge_running = False

    return {"bridge_running": bridge_running}


app.mount("/ui", StaticFiles(directory="static", html=True), name="static")

def find_free_port() -> int:
    """
    Asks the OS for any currently-available port, rather than assuming
    a hardcoded port (like 8000) is free. Binding to port 0 tells the
    OS "pick one for me" — this avoids crashing if something else on
    the user's machine already occupies our usual port.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT_FILE_PATH = "bigsip_port.txt"

if __name__ == "__main__":
    import uvicorn
    port = find_free_port()

    with open(PORT_FILE_PATH, "w") as f:
        f.write(str(port))

    print(f"Starting bigsip gateway on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)