# bigsip

Query massive local data files with an AI assistant — without uploading them, and without blowing past context window limits.

## The Problem

Large CSV/Excel files (100MB+) can't be uploaded to most AI chat interfaces due to hard file-size limits. Even when upload succeeds, the raw text of the file vastly exceeds what fits in a model's context window — a 150MB CSV is roughly 37.5 million tokens, compared to the ~1 million token limit of even large modern models.

This forces a bad workaround: pre-summarize or trim the file before ever asking a question, losing fidelity and biasing what the AI ever "sees."

## The Idea

Don't send the AI the *file*. Send it *access*.

The data stays on your machine, loaded into [DuckDB](https://duckdb.org/) — a fast, embedded analytical database. The AI is given a small set of tools to query that data (inspect the schema, run SQL) instead of ingesting it directly. It explores the structure, writes a targeted query, and gets back a small result — not the whole file.

Result: instead of millions of tokens, a typical question costs a few hundred.

## Architecture

User ↔ AI (chat) ↔ Local Gateway (FastAPI) ↔ DuckDB ↔ Your file(s)

- **Your file(s) never leave your machine.**
- The AI only ever sees: table schemas, and the (small) results of queries it writes.
- The gateway is the only thing exposed to the AI — everything else stays local.

## Status

🚧 Early development. Being built in public, phase by phase — check branches and commit history for progress. Not yet ready for real use.

## Roadmap

- [ ] Phase 1 — MVP: single CSV, local HTTP gateway, `/schema` + `/query` endpoints
- [ ] Phase 1.5 — multiple CSVs at once
- [ ] Phase 1.75 — Excel (.xlsx) support, including multi-sheet files
- [ ] Phase 2 — native MCP integration (Claude Desktop, no manual copy-pasting)
- [ ] Phase 2.5 — auto-generated system prompt (schema + relationships + custom instructions)
- [ ] Phase 3 — safety: read-only enforcement, query timeouts, row limits
- [ ] Phase 4 — simple local UI (drag files in, pick sheets/tables)
- [ ] Phase 5 — packaged as a standalone `.exe`
- [ ] Phase 6 — Docker support
- [ ] Phase 7 — CI/CD via GitHub Actions

## Prior Art

This isn't a novel pattern — several open-source DuckDB MCP servers already do something similar (e.g. `motherduckdb/mcp-server-motherduck`, `ktanaka101/mcp-server-duckdb`). `bigsip`'s goal is a simpler, easier-to-set-up version aimed at non-technical users, with a friendlier setup flow and (eventually) a one-file executable — not a claim of being first.

## License

MIT — see [LICENSE](LICENSE).