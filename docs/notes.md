# Developer Notes / Known Gotchas

Practical lessons learned while building bigsip — things that aren't bugs in the
traditional sense, but workflow/environment quirks worth knowing before you hit
them yourself.

## Restart the server after editing code

`main.py`, `engine.py`, and `bridge.py` do NOT auto-reload. If you edit any of
these files while the server or bridge is already running, the running process
keeps using the old code that was in memory when it started — your changes won't
take effect until you stop (Ctrl+C) and rerun.

This can produce confusing symptoms that look like a bug in the new code, when
really it's just stale code still running. If something that should work suddenly
doesn't, and you've recently edited a file, restart both the gateway terminal and
the bridge terminal (if running) before debugging further.

## Virtual environment activation is per-terminal

Each terminal window/tab needs its own `.\venv\Scripts\Activate.ps1` — activating
in one terminal does not carry over to a second terminal, even if both are open
at the same time. If you get a `ModuleNotFoundError` for a package you're sure
you installed, check `(venv)` is actually showing in the prompt of the terminal
where the error occurred — you may have installed the package in a different,
unactivated environment (global Python) by mistake.

## Python version matters on Windows

Very new Python versions (e.g. 3.14 at time of writing) may not yet have
prebuilt wheels for some dependencies (DuckDB, pydantic-core were both affected).
Without a wheel, pip tries to compile from source, which requires Microsoft C++
Build Tools and/or a Rust toolchain — likely not installed, and a heavy fix even
if you do install them. Simpler fix: use a well-established Python version (3.12
worked cleanly) via `py -3.12 -m venv venv` when creating the virtual environment.

## DuckDB SQL quirks (see docs/system-prompt.md for the full AI-facing version)

- Literal backslashes inside `LIKE` patterns or string equality/inequality
  comparisons (`=`, `!=`) are unreliable — they can silently return zero rows
  instead of raising an error. Use `starts_with()` for prefix matching, and
  `LENGTH()` for filtering by known string length, instead.
- To count path depth (e.g. "how many folders deep is this path"), use:
  `LENGTH("Name") - LENGTH(REPLACE("Name", '\', ''))` — this counts backslashes
  by comparing string length before and after stripping them out.
- Column names containing spaces must be double-quoted in SQL, e.g.
  `"Logical Size"`, not `Logical Size`.

## AI-generated SQL can have silent, subtle bugs

During testing, AI models occasionally dropped a single backslash character when
regenerating a query (e.g. `REPLACE("Name", '\', '')` becoming
`REPLACE("Name", '', '')`), producing a query that runs without error but returns
zero rows because the logic is now silently wrong. Worth visually double-checking
generated SQL rather than assuming "no error" means "correct."

## JSON's own escaping isn't a data problem

JSON responses will display a single backslash as `\\` (e.g. `"C:\\Users"`) —
this is standard JSON string escaping, not a sign that the actual underlying data
or your SQL needs double backslashes. The real data and real SQL only need one.

## Exception handling scope matters

Early on, the `/query` endpoint only caught `ValueError`, which meant DuckDB's own
exceptions (e.g. SQL syntax errors) went uncaught and returned a raw, non-JSON
500 error page. Since clients (like the Clipboard Bridge) expect valid JSON back
from every request, this broke the whole loop with a cryptic error. Fixed by
adding a broader `except Exception` at the API boundary — acceptable specifically
because it's the outermost layer of an HTTP endpoint, not general-purpose code.