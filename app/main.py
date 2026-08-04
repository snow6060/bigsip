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
    Reads one or more CSV file paths from command-line arguments
    (e.g. python -m app.main orders.csv customers.csv) and loads
    each into the engine as its own table before the server starts.
    """
    if len(sys.argv) < 2:
        raise RuntimeError(
            "Usage: python -m app.main <path_to_csv> [more_csvs...]"
        )

    file_paths = sys.argv[1:]
    for file_path in file_paths:
        engine.load_csv(file_path)
        print(f"Loaded '{file_path}' into table '{engine.table_names[-1]}'.")


@app.get("/schema")
def get_schema():
    """Returns structure + sample rows for every loaded table."""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)