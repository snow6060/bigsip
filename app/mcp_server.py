"""
mcp_server.py — exposes the DataEngine as MCP tools, so Claude Desktop
can call schema/query equivalents natively, without HTTP.

Unlike main.py, this doesn't take command-line file arguments —
Claude Desktop launches this script directly. For now, the file(s)
to load are set below. A proper "ask the user what to load" flow
is a Phase 4 UI concern.
"""

from mcp.server.fastmcp import FastMCP
from app.engine import DataEngine

# --- Configure which file(s) to load ---
# TODO (Phase 4): replace this with a dynamic file-selection flow.
FILES_TO_LOAD = ["c_storage_log.csv"]

mcp = FastMCP("bigsip")
engine = DataEngine()

for path in FILES_TO_LOAD:
    if path.lower().endswith(".csv"):
        engine.load_csv(path)
    elif path.lower().endswith(".xlsx"):
        engine.load_xlsx(path)


@mcp.tool()
def get_schema() -> dict:
    """
    Returns the structure of all loaded tables: column names, types,
    and a few sample rows. Call this first to understand what data
    is available before writing a query.
    """
    return engine.get_schema()


@mcp.tool()
def run_query(sql: str) -> dict:
    """
    Runs a read-only SQL SELECT query against the loaded data and
    returns the results. Only SELECT statements are allowed. Results
    are capped at 1000 rows — check the 'truncated' field in the
    response to see if more rows exist than were returned.
    """
    return engine.run_query(sql)


if __name__ == "__main__":
    mcp.run()