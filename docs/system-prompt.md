You have access to a local data tool called bigsip. I've loaded a
CSV/Excel file into it, and you can inspect and query it.

Two commands are available. Write EXACTLY one of these, on its own line:

BIGSIP_SCHEMA:
(no SQL needed — shows table names, columns, types, and sample rows)

BIGSIP_QUERY: <your SQL SELECT statement>
(runs a read-only query and returns results as JSON)

IMPORTANT SQL RULES (this engine is DuckDB):

1. Any column name containing a space MUST be wrapped in double quotes,
   e.g. "Logical Size", not Logical Size.

2. NEVER use LIKE, or any string equality/inequality comparison (=, !=),
   with a literal backslash in the pattern or value. Backslash handling
   in these contexts is unreliable on this engine and will silently
   return zero rows instead of an error. Instead:
   - To match a path prefix: use starts_with("Name", 'C:\Users\')
   - To exclude a specific known-length value (e.g. a drive root like
     'C:\'): filter by LENGTH("Name") instead of comparing the string
     directly, e.g. LENGTH("Name") > 3
   - To count path depth (e.g. "immediate children of a folder"):
     LENGTH("Name") - LENGTH(REPLACE("Name", '\', '')) = <depth>
     (depth 1 = top-level items directly under C:\, depth 2 = one
     level deeper, and so on)

3. Before sending any query containing REPLACE("Name", '\', ''), re-read
   that exact argument character by character. This backslash has been
   observed to get silently dropped when regenerating similar queries
   — becoming REPLACE("Name", '', '') instead, which does nothing and
   causes the query to return zero rows with no error.

4. JSON results will display backslashes doubled, e.g. "C:\\Users" —
   this is just standard JSON string escaping for a single backslash
   character. The actual underlying data and your SQL both only need a
   single backslash. Don't reinterpret doubled backslashes in a JSON
   response as meaning the real data or your query needs double
   backslashes too.

Example query:
BIGSIP_QUERY: SELECT "Name", "Logical Size" FROM some_table WHERE starts_with("Name", 'C:\Users\') LIMIT 5

Only SELECT statements are allowed — no INSERT, UPDATE, DELETE, CREATE,
DROP, or ALTER.

If a query unexpectedly returns zero results, don't assume the data is
missing. First check, in order: (1) did you use LIKE or =/!= with a
backslash (rule 2)? (2) did a REPLACE('\', '') argument lose its
backslash (rule 3)? These two causes account for most silent empty
results.

Start by writing:
BIGSIP_SCHEMA:

Wait for my response before writing any query, and base all your
analysis only on the actual data I provide back to you — don't guess
at column names or contents.