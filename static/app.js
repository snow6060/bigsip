const API_BASE = "";
let loadedFiles = []; // { path, tables: [] }
let currentMode = localStorage.getItem("bigsip_mode"); // "mcp" | "browser" | null

// ── DOM references ──
const modeChoiceScreen = document.getElementById("mode-choice-screen");
const appShell = document.getElementById("app-shell");
const browserPanel = document.getElementById("browser-panel");
const mcpPanel = document.getElementById("mcp-panel");

const selectFilesBtn = document.getElementById("select-files-btn");
const loadedFilesList = document.getElementById("loaded-files-list");
const schemaSection = document.getElementById("schema-section");
const schemaDisplay = document.getElementById("schema-display");

const querySection = document.getElementById("query-section");
const queryToggle = document.getElementById("query-toggle");
const queryBody = document.getElementById("query-body");
const queryInput = document.getElementById("query-input");
const runQueryBtn = document.getElementById("run-query-btn");
const queryResults = document.getElementById("query-results");

const promptContext = document.getElementById("prompt-context");
const copyPromptBtn = document.getElementById("copy-prompt-btn");

const statusDisplay = document.getElementById("status-display");
const bridgeStatusEl = document.getElementById("bridge-status");
const mcpStatusEl = document.getElementById("mcp-status");

const guideOverlay = document.getElementById("guide-overlay");

// ── Wait for pywebview's JS bridge to be ready ──
function whenPywebviewReady(callback) {
    if (window.pywebview && window.pywebview.api) {
        callback();
    } else {
        window.addEventListener("pywebviewready", callback, { once: true });
    }
}

// ── Mode selection ──
document.querySelectorAll(".mode-card").forEach(card => {
    card.addEventListener("click", () => setMode(card.dataset.mode));
});

function setMode(mode) {
    currentMode = mode;
    localStorage.setItem("bigsip_mode", mode);
    showAppShell();
}

function showAppShell() {
    modeChoiceScreen.classList.add("hidden");
    appShell.classList.remove("hidden");

    if (currentMode === "browser") {
        browserPanel.classList.remove("hidden");
        mcpPanel.classList.add("hidden");
        bridgeStatusEl.classList.remove("hidden");
        mcpStatusEl.classList.add("hidden");
        whenPywebviewReady(() => window.pywebview.api.start_bridge());
        checkBridgeStatus();
        setInterval(checkBridgeStatus, 2000);
    } else if (currentMode === "mcp") {
        mcpPanel.classList.remove("hidden");
        browserPanel.classList.add("hidden");
        mcpStatusEl.classList.remove("hidden");
        bridgeStatusEl.classList.add("hidden");
        refreshMcpStatus();
        setInterval(refreshMcpStatus, 3000);
    }
}

if (currentMode) {
    showAppShell();
}

// ── Sidebar nav ──
document.getElementById("nav-change-mode").addEventListener("click", () => {
    if (currentMode === "browser") {
        whenPywebviewReady(() => window.pywebview.api.stop_bridge());
    }
    appShell.classList.add("hidden");
    modeChoiceScreen.classList.remove("hidden");
});

document.getElementById("nav-guide").addEventListener("click", () => {
    guideOverlay.classList.remove("hidden");
});

document.getElementById("guide-close-btn").addEventListener("click", () => {
    guideOverlay.classList.add("hidden");
});

document.getElementById("nav-reset").addEventListener("click", () => {
    if (!confirm("Reset session? This closes and reopens the app.")) return;
    whenPywebviewReady(() => window.pywebview.api.restart_app());
});

// ── File loading (native dialog) ──
selectFilesBtn.addEventListener("click", () => {
    whenPywebviewReady(async () => {
        const paths = await window.pywebview.api.select_files();
        for (const path of paths) {
            await loadFile(path);
        }
        if (currentMode === "mcp") {
            syncMcpFiles();
        }
    });
});

async function loadFile(filePath) {
    try {
        const response = await fetch(`${API_BASE}/load`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_path: filePath }),
        });

        if (!response.ok) {
            const error = await response.json();
            alert(`Failed to load "${filePath}": ${error.detail}`);
            return;
        }

        const result = await response.json();
        loadedFiles.push({ path: filePath, tables: result.loaded_tables });

        renderFilesList();
        schemaSection.classList.remove("hidden");
        querySection.classList.remove("hidden");
        await refreshSchema();
    } catch (err) {
        alert(`Error loading file: ${err.message}`);
    }
}

function renderFilesList() {
    loadedFilesList.innerHTML = "";
    loadedFiles.forEach(f => {
        const li = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = `${f.path} → ${f.tables.join(", ")}`;
        const removeBtn = document.createElement("button");
        removeBtn.textContent = "✕";
        removeBtn.className = "file-remove-btn";
        removeBtn.addEventListener("click", () => removeFile(f));
        li.appendChild(label);
        li.appendChild(removeBtn);
        loadedFilesList.appendChild(li);
    });
}

async function removeFile(fileEntry) {
    for (const tableName of fileEntry.tables) {
        try {
            await fetch(`${API_BASE}/table/${tableName}`, { method: "DELETE" });
        } catch (err) {
            console.error(`Failed to drop table ${tableName}:`, err);
        }
    }
    loadedFiles = loadedFiles.filter(f => f !== fileEntry);
    renderFilesList();
    await refreshSchema();
    if (currentMode === "mcp") syncMcpFiles();

    if (loadedFiles.length === 0) {
        schemaSection.classList.add("hidden");
    }
}

function syncMcpFiles() {
    whenPywebviewReady(() => {
        window.pywebview.api.set_mcp_files(loadedFiles.map(f => f.path));
    });
}

// ── Schema — partial view, expand on click ──
async function refreshSchema() {
    const response = await fetch(`${API_BASE}/schema`);
    if (!response.ok) {
        schemaDisplay.innerHTML = "";
        return;
    }
    const data = await response.json();

    let html = "";
    data.tables.forEach(table => {
        html += `<div class="schema-table-header" data-table="${table.table_name}">
            <span><strong>${table.table_name}</strong> — ${table.columns.length} columns</span>
            <span>▸</span>
        </div>
        <div class="schema-table-detail hidden" id="detail-${table.table_name}">
            <ul>`;
        table.columns.forEach(col => {
            html += `<li>${col.name} <span style="color:var(--bigsip-text-muted);">(${col.type})</span></li>`;
        });
        html += `</ul></div>`;
    });

    schemaDisplay.innerHTML = html;

    document.querySelectorAll(".schema-table-header").forEach(header => {
        header.addEventListener("click", () => {
            const detail = document.getElementById(`detail-${header.dataset.table}`);
            detail.classList.toggle("hidden");
        });
    });
}

// ── Query tester (collapsed by default) ──
queryToggle.addEventListener("click", () => {
    queryBody.classList.toggle("hidden");
});

runQueryBtn.addEventListener("click", async () => {
    const sql = queryInput.value.trim();
    if (!sql) return;
    queryResults.textContent = "Running...";

    try {
        const response = await fetch(`${API_BASE}/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql }),
        });
        const data = await response.json();

        if (!response.ok) {
            queryResults.textContent = `Error: ${data.detail}`;
            return;
        }
        renderQueryResults(data);
    } catch (err) {
        queryResults.textContent = `Error: ${err.message}`;
    }
});

function renderQueryResults(data) {
    if (data.rows.length === 0) {
        queryResults.textContent = "No rows returned.";
        return;
    }
    const columns = Object.keys(data.rows[0]);
    let html = "<table><thead><tr>";
    columns.forEach(col => html += `<th>${col}</th>`);
    html += "</tr></thead><tbody>";
    data.rows.forEach(row => {
        html += "<tr>";
        columns.forEach(col => html += `<td>${row[col]}</td>`);
        html += "</tr>";
    });
    html += "</tbody></table>";
    if (data.truncated) {
        html += `<p style="margin-top: 8px; color: var(--bigsip-text-muted);">Showing first ${data.row_limit} rows (truncated).</p>`;
    }
    queryResults.innerHTML = html;
}

// ── Prompt copy ──
copyPromptBtn.addEventListener("click", async () => {
    const context = promptContext.value.trim();
    const url = context
        ? `${API_BASE}/prompt?context=${encodeURIComponent(context)}`
        : `${API_BASE}/prompt`;
    try {
        const response = await fetch(url);
        const text = await response.text();
        await navigator.clipboard.writeText(text);
        copyPromptBtn.textContent = "Copied!";
        setTimeout(() => { copyPromptBtn.textContent = "Copy Prompt"; }, 1500);
    } catch (err) {
        alert(`Failed to copy prompt: ${err.message}`);
    }
});

// ── Status (sidebar) ──
async function refreshStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        const data = await response.json();
        statusDisplay.textContent = `Uptime: ${data.uptime_seconds}s\nMemory: ${data.memory_usage}`;
    } catch {
        statusDisplay.textContent = "Unavailable";
    }
}
refreshStatus();
setInterval(refreshStatus, 3000);

async function checkBridgeStatus() {
    try {
        const response = await fetch(`${API_BASE}/bridge-status`);
        const data = await response.json();
        bridgeStatusEl.textContent = data.bridge_running
            ? "🟢 Clipboard Bridge: Active"
            : "⚪ Clipboard Bridge: Not running";
    } catch {
        bridgeStatusEl.textContent = "⚪ Clipboard Bridge: Not running";
    }
}

// ── MCP status + setup ──
const mcpStatusBadge = document.getElementById("mcp-status-badge");
const mcpSetupBlock = document.getElementById("mcp-setup-block");
const mcpSetupMessage = document.getElementById("mcp-setup-message");

function refreshMcpStatus() {
    whenPywebviewReady(async () => {
        const result = await window.pywebview.api.check_mcp_status();
        const status = result.status;

        mcpStatusBadge.className = `status-badge ${status}`;
        const labels = {
            not_configured: "MCP Server: Not set up",
            configured: "MCP Server: Configured — not currently running",
            online: "MCP Server: Online ✓",
        };
        mcpStatusBadge.textContent = labels[status];
        mcpStatusEl.textContent = labels[status];

        mcpSetupBlock.classList.toggle("hidden", status !== "not_configured");
    });
}

document.getElementById("mcp-setup-auto-btn").addEventListener("click", () => {
    whenPywebviewReady(async () => {
        const result = await window.pywebview.api.setup_mcp();
        showMcpSetupResult(result);
    });
});

document.getElementById("mcp-setup-manual-btn").addEventListener("click", () => {
    const path = document.getElementById("mcp-manual-path").value.trim();
    if (!path) return;
    whenPywebviewReady(async () => {
        const result = await window.pywebview.api.setup_mcp(path);
        showMcpSetupResult(result);
    });
});

function showMcpSetupResult(result) {
    mcpSetupMessage.classList.remove("hidden");
    mcpSetupMessage.textContent = result.success
        ? "MCP configured. Restart Claude Desktop for it to take effect."
        : `Setup failed: ${result.error}`;
    if (result.success) refreshMcpStatus();
}