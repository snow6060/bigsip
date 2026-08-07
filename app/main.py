"""
main.py — the web layer. Defines HTTP endpoints and translates
HTTP requests into calls on the DataEngine.
"""

import sys
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
from app.engine import DataEngine

app = FastAPI(title="bigsip gateway")
engine = DataEngine()


class QueryRequest(BaseModel):
    sql: str


@app.on_event("startup")
def load_data_on_startup():
    if len(sys.argv) < 2:
        raise RuntimeError(
            "Usage: python -m app.main <file1.csv|xlsx> [more files...]"
        )

    file_paths = sys.argv[1:]
    for file_path in file_paths:
        ext = Path(file_path).suffix.lower()

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


@app.get("/schema")
def get_schema():
    try:
        return engine.get_schema()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/query")
def run_query(request: QueryRequest):
    try:
        return {"results": engine.run_query(request.sql)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catches DuckDB's own exceptions (syntax errors, etc.) that
        # aren't ValueErrors, so the client always gets valid JSON back
        # instead of a raw 500 error page.
        raise HTTPException(status_code=400, detail=f"Query failed: {str(e)}")


STATIC_PROMPT_PATH = Path(__file__).parent.parent / "docs" / "system-prompt.md"


@app.get("/prompt", response_class=PlainTextResponse)
def get_prompt(context: str | None = None):
    """
    Generates a ready-to-paste system prompt: the static DuckDB/AI rules
    (read from docs/system-prompt.md) combined with the live schema of
    whatever's currently loaded, plus optional user-provided context.
    """
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)