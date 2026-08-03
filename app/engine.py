"""
engine.py — owns all interaction with DuckDB.
Knows nothing about HTTP, FastAPI, or the web. Its only job:
load a CSV, describe its structure, and run read-only queries against it.
"""

import duckdb

# Keywords that indicate a write/destructive operation.
# Phase 1 keeps this simple; Phase 3 will harden it properly.
_FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter",
    "create", "attach", "copy", "pragma", "install", "load"
]


class DataEngine:
    def __init__(self):
        # ':memory:' means the database lives only in RAM — nothing
        # is written to disk. When the process exits, it's gone.
        self.con = duckdb.connect(database=":memory:")
        self.table_name = None

    def load_csv(self, file_path: str, table_name: str = "data"):
        """
        Loads a CSV file into DuckDB as a queryable table.
        read_csv_auto lets DuckDB guess delimiters, types, and headers.
        """
        self.con.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)",
            [file_path],
        )
        self.table_name = table_name

    def get_schema(self) -> dict:
        """
        Returns column names/types, plus a small sample of rows,
        so an AI (or a human testing manually) can understand
        the data's shape before writing a query.
        """
        if self.table_name is None:
            raise RuntimeError("No table loaded yet.")

        columns = self.con.execute(
            f"DESCRIBE {self.table_name}"
        ).fetchall()

        sample = self.con.execute(
            f"SELECT * FROM {self.table_name} LIMIT 5"
        ).fetchall()

        column_names = [col[0] for col in columns]

        return {
            "table_name": self.table_name,
            "columns": [
                {"name": col[0], "type": col[1]} for col in columns
            ],
            "sample_rows": [
                dict(zip(column_names, row)) for row in sample
            ],
        }

    def run_query(self, sql: str) -> list[dict]:
        """
        Executes a read-only SQL query and returns rows as a list of dicts.
        Blocks obvious write/destructive statements by keyword check.
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