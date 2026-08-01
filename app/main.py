"""
main.py — the web layer. Defines HTTP endpoints and translates
HTTP requests into calls on the DataEngine. Knows nothing about
DuckDB internals — just calls engine.py's public methods.
"""

import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.engine import DataEngine

app = FastAPI(title="bigsip gateway")
engine = DataEngine()


class QueryRequest(BaseModel):
    sql: str


@app.on_event("startup")
def load_data_on_startup():
    """
    Reads the CSV file path from a command-line argument
    (passed when running: python -m app.main path/to/file.csv)
    and loads it into the engine before the server starts accepting requests.
    """
    if len(sys.argv) < 2:
        raise RuntimeError(
            "Usage: python -m app.main <path_to_csv>"
        )
    file_path = sys.argv[1]
    engine.load_csv(file_path)
    print(f"Loaded '{file_path}' into table 'data'.")


@app.get("/schema")
def get_schema():
    """Returns table structure + sample rows."""
    try:
        return engine.get_schema()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/query")
def run_query(request: QueryRequest):
    """Runs a read-only SQL query, returns results as JSON."""
    try:
        return {"results": engine.run_query(request.sql)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))