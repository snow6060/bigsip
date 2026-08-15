const API_BASE = ""; // same origin, since we're served by the same FastAPI app

let loadedTables = [];

// ── DOM references ──
const selectFilesBtn = document.getElementById("select-files-btn");
const fileInput = document.getElementById("file-input");
const loadedFilesList = document.getElementById("loaded-files-list");

const schemaSection = document.getElementById("schema-section");
const schemaDisplay = document.getElementById("schema-display");

const querySection = document.getElementById("query-section");
const queryInput = document.getElementById("query-input");
const runQueryBtn = document.getElementById("run-query-btn");
const queryResults = document.getElementById("query-results");

const promptSection = document.getElementById("prompt-section");
const promptContext = document.getElementById("prompt-context");
const copyPromptBtn = document.getElementById("copy-prompt-btn");

const statusSection = document.getElementById("status-section");
const bridgeStatusEl = document.getElementById("bridge-status");
const statusDisplay = document.getElementById("status-display");

// ── File selection ──
selectFilesBtn.addEventListener("click", () => {
    fileInput.click();
});

fileInput.addEventListener("change", async (event) => {
    const files = Array.from(event.target.files);

    for (const file of files) {
        // Browsers generally do NOT expose the full system path for
        // security reasons — file.name is usually all we get. We ask
        // the user to confirm/complete the full path, since our backend
        // needs a real filesystem path (not the file's bytes) to load it.
        const fullPath = prompt(`Paste the full path to "${file.name}":`, "Paste path here");

        if (!fullPath) continue; // user cancelled

        await loadFile(fullPath);
    }
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
        loadedTables.push(...result.loaded_tables);

        addFileToList(filePath, result.loaded_tables);
        revealSections();
        await refreshSchema();
        await refreshStatus();
    } catch (err) {
        alert(`Error loading file: ${err.message}`);
    }
}

function addFileToList(filePath, tables) {
    const li = document.createElement("li");
    li.textContent = `${filePath} → ${tables.join(", ")}`;
    loadedFilesList.appendChild(li);
}

function revealSections() {
    schemaSection.classList.remove("hidden");
    querySection.classList.remove("hidden");
    promptSection.classList.remove("hidden");
    statusSection.classList.remove("hidden");
}

// ── Schema display ──
async function refreshSchema() {
    const response = await fetch(`${API_BASE}/schema`);
    const data = await response.json();

    let html = "";
    data.tables.forEach(table => {
        html += `<h3>${table.table_name}</h3><ul>`;
        table.columns.forEach(col => {
            html += `<li>${col.name} <span style="color:#5a6b7d;">(${col.type})</span></li>`;
        });
        html += "</ul>";
    });

    schemaDisplay.innerHTML = html;
}

// ── Query runner ──
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
        html += `<p style="margin-top: 8px; color: #8a97a8;">Showing first ${data.row_limit} rows (truncated).</p>`;
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

// ── Status dashboard ──
async function refreshStatus() {
    const response = await fetch(`${API_BASE}/status`);
    const data = await response.json();

    statusDisplay.textContent = JSON.stringify(data, null, 2);
}

// ── Bridge status ──
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

checkBridgeStatus();
setInterval(checkBridgeStatus, 2000);
