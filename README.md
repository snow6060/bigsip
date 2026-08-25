# bigsip

Query massive local CSV/Excel files with an AI assistant — without uploading them, and without blowing past context window limits.

Your data never leaves your computer. bigsip runs entirely locally, giving your AI assistant a way to explore and query your files through SQL instead of reading the raw file contents.

## The Problem

Large CSV/Excel files (100MB+) can't be uploaded to most AI chat interfaces due to hard file-size limits. Even when upload succeeds, the raw text of the file vastly exceeds what fits in a model's context window — a 150MB CSV is roughly 37.5 million tokens, compared to the ~1 million token limit of even large modern models.

bigsip solves this by giving the AI *access*, not the file itself — it explores your data's structure, writes a targeted SQL query, and gets back a small, relevant result instead of the whole file.

## Download

**Windows:** Download the latest `bigsip.zip` from the [Releases](https://github.com/snow6060/bigsip/releases) page, unzip it anywhere, and run `bigsip.exe` inside the extracted folder.

No installation, no Python required — everything needed is bundled inside.

*(macOS/Linux: not yet packaged — see "Running from Source" below.)*

## Getting Started

1. **Open bigsip.** A window opens showing two options: **MCP Server** (for Claude Desktop) or **Browser-Based Agents** (DeepSeek, Gemini, ChatGPT, or any other browser AI chat). Pick whichever matches the AI you actually use.
2. **Load your file(s).** Click "Select File(s)" and pick a CSV or Excel file — nothing is uploaded, the file stays on your computer.
3. **Copy the system prompt.** One click copies it. Paste it as your first message to your AI — this teaches it how to talk to your data.
4. **Ask your question.**
   - *Browser-Based Agents mode:* just ask normally in the chat — bigsip watches your clipboard and relays the AI's data requests automatically.
   - *MCP Server mode:* set up the connection once (a button on that screen), restart Claude Desktop, then ask it about your data directly — no copy-pasting, ever again.

Full step-by-step instructions are also built into the app itself (sidebar → **User Guide**).

## How It Works

```
User ↔ AI (chat) ↔ Local Gateway (FastAPI) ↔ DuckDB ↔ Your file(s)
```

- Your file(s) never leave your machine.
- The AI only ever sees table schemas and the small results of the queries it writes.
- Two independent ways for an AI to reach the local gateway: a native **MCP** connection (Claude Desktop), or an **in-app Clipboard Bridge** that relays requests for any browser-based AI chat that has no built-in tool-calling.

## Running From Source

If you'd rather run it from source (or you're on macOS/Linux):

```powershell
git clone https://github.com/snow6060/bigsip.git
cd bigsip
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows
pip install -r requirements.txt
python -m app.desktop
```

Requires Python 3.12 (newer versions may fail to build DuckDB's dependencies from source — see `docs/notes.md`).

## Status

Actively developed. Core functionality (MCP integration, Clipboard Bridge, native desktop app, packaged Windows build) is complete and tested against real large/messy files. See `docs/case-study.md` for real-world validation, and `docs/notes.md` for known quirks and gotchas.

## Roadmap

- [x] Phase 1 — MVP: single CSV, local HTTP gateway, `/schema` + `/query` endpoints
- [x] Phase 1.5 — multiple CSVs at once
- [x] Phase 1.75 — Excel (.xlsx) support, including multi-sheet files
- [x] Phase 2 — native MCP integration (Claude Desktop, no manual copy-pasting)
- [x] Phase 2.5 — auto-generated system prompt (schema + relationships + custom instructions)
- [x] Phase 3 — safety: read-only enforcement, query timeouts, row limits
- [x] Phase 4 — simple local UI (drag files in, pick sheets/tables)
- [x] Phase 5 — packaged as a standalone `.exe` (Windows, one-folder build)
- [ ] Phase 5.5 — proper installer (single download, Start Menu entry, uninstaller)
- [ ] Phase 6 — Docker support
- [ ] Phase 7 — CI/CD via GitHub Actions

## Prior Art

This isn't a novel pattern — several open-source DuckDB MCP servers already do something similar (e.g. `motherduckdb/mcp-server-motherduck`, `ktanaka101/mcp-server-duckdb`). bigsip's goal is a simpler, easier-to-set-up version aimed at non-technical users, with a friendlier setup flow and a one-file-download experience — not a claim of being first.

## License

MIT — see [LICENSE](LICENSE).
