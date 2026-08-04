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
# Phase 1 keeps this simple; Phase 3 will harden it properly.
_FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter",
    "create", "attach", "copy", "pragma", "install", "load"
]


def _sanitize_name(raw: str) -> str:
    """
    Turns arbitrary text (filename or sheet name) into a safe
    SQL identifier fragment. e.g. 'My Sales (2024)' -> 'my_sales_2024'
    """
    lowered = raw.lower()
    sanitized = re.sub(r"[^a-z0-9_]", "_", lowered)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized


def _sanitize_table_name(file_path: str) -> str:
    """Derives a safe table name from a file path (no sheet involved)."""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    sanitized = _sanitize_name(base_name)

    if not sanitized or not sanitized[0].isalpha():
        sanitized = f"table_{sanitized}" if sanitized else "table_unnamed"

    return sanitized


class DataEngine:
    def __init__(self):
        # ':memory:' means the database lives only in RAM — nothing
        # is written to disk. When the process exits, it's gone.
        self.con = duckdb.connect(database=":memory:")
        self.table_names: list[str] = []

    def _register_table_name(self, table_name: str):
        """Shared collision check, used by both CSV and xlsx loaders."""
        if table_name in self.table_names:
            raise ValueError(
                f"Table name '{table_name}' is already in use. "
                f"Rename the file/sheet or choose a different table name."
            )
        self.table_names.append(table_name)

    def load_csv(self, file_path: str, table_name: str | None = None):
        """Loads a CSV file into DuckDB as a queryable table."""
        if table_name is None:
            table_name = _sanitize_table_name(file_path)

        self._register_table_name(table_name)

        self.con.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)",
            [file_path],
        )

    def load_xlsx(self, file_path: str):
        """
        Loads every sheet in an xlsx file as its own DuckDB table.
        Table names follow the pattern '{filename}_{sheetname}', sanitized.

        Assumes row 1 of each sheet is the header row — messier headers
        (title rows, merged cells) are a known limitation, not handled here.
        """
        base_name = _sanitize_table_name(file_path)
        workbook = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))

            if not rows:
                continue  # skip genuinely empty sheets

            headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
            data_rows = rows[1:]
            records = [dict(zip(headers, row)) for row in data_rows]

            table_name = f"{base_name}_{_sanitize_name(sheet_name)}"
            self._register_table_name(table_name)

            # DuckDB can register a pandas DataFrame directly as a
            # queryable virtual table — plain Python lists aren't supported.
            df = pandas.DataFrame(records)
            self.con.register("temp_sheet_view", df)
            self.con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_sheet_view")
            self.con.unregister("temp_sheet_view")

        workbook.close()

    def get_schema(self) -> dict:
        """
        Returns column names/types + a small sample of rows,
        for every loaded table.
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