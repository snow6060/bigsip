"""
engine.py — owns all interaction with DuckDB.
Knows nothing about HTTP, FastAPI, or the web. Its only job:
load CSV/xlsx file(s), describe their structure, and run read-only queries.
"""

import os
import re
import duckdb
import openpyxl
import pandas

# Keywords that indicate a write/destructive operation.
# Matched as whole words, not substrings, to reduce false positives/bypasses.
_FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter",
    "create", "attach", "copy", "pragma", "install", "load"
]

_MAX_ROWS = 1000  # hard cap on rows returned by any query


def _sanitize_name(raw: str) -> str:
    lowered = raw.lower()
    sanitized = re.sub(r"[^a-z0-9_]", "_", lowered)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized


def _sanitize_table_name(file_path: str) -> str:
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    sanitized = _sanitize_name(base_name)
    if not sanitized or not sanitized[0].isalpha():
        sanitized = f"table_{sanitized}" if sanitized else "table_unnamed"
    return sanitized


def _contains_forbidden_keyword(sql: str) -> str | None:
    """
    Checks for forbidden keywords as whole words (not substrings of other
    words), using word boundaries. Returns the matched keyword, or None
    if the query is clean.
    """
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", sql, re.IGNORECASE):
            return keyword
    return None


class DataEngine:
    def __init__(self):
        # ':memory:' means the database lives only in RAM — nothing
        # is written to disk. When the process exits, it's gone.
        self.con = duckdb.connect(database=":memory:")
        self.table_names: list[str] = []

        # Cap DuckDB's own memory usage as a safeguard against a runaway
        # query consuming all available RAM. This doesn't stop a slow
        # query, but it prevents the worst-case failure mode.
        self.con.execute("SET memory_limit = '2GB'")

    def _register_table_name(self, table_name: str):
        if table_name in self.table_names:
            raise ValueError(
                f"Table name '{table_name}' is already in use. "
                f"Rename the file/sheet or choose a different table name."
            )
        self.table_names.append(table_name)

    def load_csv(self, file_path: str, table_name: str | None = None):
        if table_name is None:
            table_name = _sanitize_table_name(file_path)

        self._register_table_name(table_name)

        self.con.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)",
            [file_path],
        )

    def load_xlsx(self, file_path: str):
        base_name = _sanitize_table_name(file_path)
        workbook = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))

            if not rows:
                continue

            headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
            data_rows = rows[1:]
            records = [dict(zip(headers, row)) for row in data_rows]

            table_name = f"{base_name}_{_sanitize_name(sheet_name)}"
            self._register_table_name(table_name)

            df = pandas.DataFrame(records)
            self.con.register("temp_sheet_view", df)
            self.con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_sheet_view")
            self.con.unregister("temp_sheet_view")

        workbook.close()

    def get_schema(self) -> dict:
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

    def validate_query(self, sql: str):
        """
        Checks a query for safety issues WITHOUT executing it:
        - must start with SELECT
        - must not contain forbidden keywords (as whole words)
        - must be syntactically valid, checked via EXPLAIN (which plans
          the query without running it)
        Raises ValueError with a clear message if any check fails.
        """
        lowered = sql.strip().lower()

        if not lowered.startswith("select"):
            raise ValueError("Only SELECT queries are allowed.")

        forbidden = _contains_forbidden_keyword(sql)
        if forbidden:
            raise ValueError(f"Query contains forbidden keyword: '{forbidden}'")

        try:
            self.con.execute(f"EXPLAIN {sql}")
        except Exception as e:
            raise ValueError(f"Query failed validation (syntax error): {str(e)}")

    def run_query(self, sql: str) -> dict:
        """
        Validates, then executes a read-only SQL query. Returns results
        as a list of dicts, capped at _MAX_ROWS. Indicates in the
        response if results were truncated.
        """
        self.validate_query(sql)

        result = self.con.execute(sql)
        column_names = [desc[0] for desc in result.description]
        rows = result.fetchmany(_MAX_ROWS + 1)  # fetch one extra to detect truncation

        truncated = len(rows) > _MAX_ROWS
        if truncated:
            rows = rows[:_MAX_ROWS]

        return {
            "rows": [dict(zip(column_names, row)) for row in rows],
            "truncated": truncated,
            "row_limit": _MAX_ROWS,
        }