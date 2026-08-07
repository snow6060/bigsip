"""
main.py — the web layer. Defines HTTP endpoints and translates
HTTP requests into calls on the DataEngine.
"""

import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)