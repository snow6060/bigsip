"""
engine.py — owns all interaction with DuckDB.
Knows nothing about HTTP, FastAPI, or the web. Its only job:
load CSV file(s), describe their structure, and run read-only queries.
"""

import os
import re
import duckdb

# Keywords that indicate a write/destructive operation.
# Phase 1 keeps this simple; Phase 3 will harden it properly.
_FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter",
    "create", "attach", "copy", "pragma", "install", "load"
]


def _sanitize_table_name(file_path: str) -> str:
    """
    Turns a filename into a safe SQL table name.
    e.g. 'My Sales (2024).csv' -> 'my_sales_2024'
    """
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    lowered = base_name.lower()
    # Replace anything that isn't a letter, digit, or underscore with '_'
    sanitized = re.sub(r"[^a-z0-9_]", "_", lowered)
    # Collapse multiple underscores, strip leading/trailing ones
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")

    if not sanitized or not sanitized[0].isalpha():
        # SQL table names shouldn't start with a digit or be empty
        sanitized = f"table_{sanitized}" if sanitized else "table_unnamed"

    return sanitized


class DataEngine:
    def __init__(self):
        # ':memory:' means the database lives only in RAM — nothing
        # is written to disk. When the process exits, it's gone.
        self.con = duckdb.connect(database=":memory:")
        self.table_names: list[str] = []

    def load_csv(self, file_path: str, table_name: str | None = None):
        """
        Loads a CSV file into DuckDB as a queryable table.
        If table_name isn't given, it's derived from the filename.
        Raises an error on name collision rather than silently overwriting.
        """
        if table_name is None:
            table_name = _sanitize_table_name(file_path)

        if table_name in self.table_names:
            raise ValueError(
                f"Table name '{table_name}' is already in use. "
                f"Rename the file or choose a different table name."
            )

        self.con.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)",
            [file_path],
        )
        self.table_names.append(table_name)

    def get_schema(self) -> dict:
        """
        Returns column names/types + a small sample of rows,
        for every loaded table — so an AI (or a human testing
        manually) can see everything available to query.
        """
        if not self.table_names:
            raise RuntimeError("No tables loaded yet.")

        tables = []
        for table_name in self.table_names:
            columns = self.con.execute(f"DESCRIBE {table_name}").fetchall()
            sample = self.con.execute(
                f"SELECT * FROM {table_name} LIMIT 5"
            ).fetchall()
            column_names = [col[0] for col in columns]

            tables.append({
                "table_name": table_name,
                "columns": [
                    {"name": col[0], "type": col[1]} for col in columns
                ],
                "sample_rows": [
                    dict(zip(column_names, row)) for row in sample
                ],
            })

        return {"tables": tables}

    def run_query(self, sql: str) -> list[dict]:
        """
        Executes a read-only SQL query and returns rows as a list of dicts.
        Blocks obvious write/destructive statements by keyword check.
        Works across any loaded tables, including JOINs between them.
        """
        lowered = sql.strip().lower()

        if not lowered.startswith("select"):
            raise ValueError("Only SELECT queries are allowed.")

        for keyword in _FORBIDDEN_KEYWORDS:
            if keyword in lowered:
                raise ValueError(f"Query contains forbidden keyword: '{keyword}'")

        result = self.con.execute(sql)
        column_names = [desc[0] for desc in result.description]
        rows = result.fetchall()

        return [dict(zip(column_names, row)) for row in rows]