"""
xlsx_worker.py — runs in a SEPARATE OS PROCESS (via ProcessPoolExecutor
in main.py) to parse large multi-sheet xlsx files without blocking the
main app's GIL. Only parses and writes to Parquet — never touches
DuckDB directly, since DataEngine's connection lives in the main
process and can't be shared/pickled across processes.

Must stay a top-level, importable function — Windows' process-spawning
strategy pickles a reference to this function by module path, not the
function object itself, so it can't be a closure or a method.
"""

import json
import os
import re
from pathlib import Path

import pandas as pd
import openpyxl


def _sanitize(raw: str) -> str:
    lowered = raw.lower()
    sanitized = re.sub(r"[^a-z0-9_]", "_", lowered)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized


def load_xlsx_to_parquet(
    file_path: str,
    sheets: list[str] | None,
    temp_dir: str,
    progress_path: str,
) -> dict:
    """
    Reads each sheet of file_path, writes it to a Parquet file in
    temp_dir, and updates progress_path after each sheet starts.
    Returns a manifest: {"tables": [{"table_name": ..., "parquet_path": ...}], "error": None}
    on success, or {"tables": [], "error": "..."} on failure.
    """
    progress_file = Path(progress_path)

    def _write_progress(current, total, sheet_name, status="in_progress"):
        progress_file.write_text(json.dumps({
            "status": status,
            "current_sheet": current,
            "total_sheets": total,
            "sheet_name": sheet_name,
        }), encoding="utf-8")

    try:
        base_name = _sanitize(os.path.splitext(os.path.basename(file_path))[0])
        if not base_name or not base_name[0].isalpha():
            base_name = f"table_{base_name}" if base_name else "table_unnamed"

        workbook = openpyxl.load_workbook(file_path, read_only=True)
        sheet_names_to_load = sheets if sheets is not None else workbook.sheetnames
        workbook.close()

        total = len(sheet_names_to_load)
        tables = []
        temp_path = Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)

        for i, sheet_name in enumerate(sheet_names_to_load, start=1):
            _write_progress(i, total, sheet_name)

            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
            if df.empty:
                continue

            table_name = f"{base_name}_{_sanitize(sheet_name)}"
            parquet_path = temp_path / f"{table_name}.parquet"
            # Some real-world spreadsheets have columns with genuinely mixed types
            # (e.g. a stray date accidentally entered in a text column) — pandas
            # reads these as 'object' dtype holding a mix of types, which Parquet
            # can't write directly (it requires one consistent type per column).
            # Coerce only the actual non-string values in such columns to strings,
            # preserving real strings and NaN/None as-is, rather than failing the
            # whole file over one inconsistent cell.
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].apply(
                        lambda v: v if (v is None or isinstance(v, str)) else str(v)
                    )
            df.to_parquet(parquet_path)

            tables.append({"table_name": table_name, "parquet_path": str(parquet_path)})

        _write_progress(total, total, "", status="complete")
        return {"tables": tables, "error": None}

    except Exception as e:
        progress_file.write_text(json.dumps({
            "status": "error",
            "error": str(e),
        }), encoding="utf-8")
        return {"tables": [], "error": str(e)}