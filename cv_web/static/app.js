const state = {
    isRunning: false,
    activeTab: "cv",
    activeLogTab: "run",
    isDraggingSplitter: false,
    diskFiles: {},
};

const els = {
    statusText: document.getElementById("statusText"),
    cvEditor: document.getElementById("cvEditor"),
    promptEditor: document.getElementById("promptEditor"),
    jobspecEditor: document.getElementById("jobspecEditor"),
    envEditor: document.getElementById("envEditor"),
    tailoredViewer: document.getElementById("tailoredViewer"),
    runFormatBtn: document.getElementById("runFormatBtn"),
    runFullBtn: document.getElementById("runFullBtn"),
    runLogOutput: document.getElementById("runLogOutput"),
    debugLogOutput: document.getElementById("debugLogOutput"),
    refreshLogsBtn: document.getElementById("refreshLogsBtn"),
    logSelect: document.getElementById("logSelect"),
    pdfPreview: document.getElementById("pdfPreview"),
    layout: document.querySelector(".layout"),
    paneSplitter: document.getElementById("paneSplitter"),
    tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
    tabLabels: Array.from(document.querySelectorAll(".tab-label")),
    fileLoadButtons: Array.from(document.querySelectorAll(".file-load-btn")),
    fileSaveButtons: Array.from(document.querySelectorAll(".file-save-btn")),
    tabPanels: {
        cv: document.getElementById("tab-cv"),
        prompt: document.getElementById("tab-prompt"),
        jobspec: document.getElementById("tab-jobspec"),
        env: document.getElementById("tab-env"),
        tailored: document.getElementById("tab-tailored"),
        logs: document.getElementById("tab-logs"),
    },
    logTabButtons: Array.from(document.querySelectorAll(".log-tab-btn")),
    logPanels: {
        run: document.getElementById("log-panel-run"),
        debug: document.getElementById("log-panel-debug"),
    },
};

const EDITABLE_FILES = {
    cv: { tabLabel: "CV", title: document.getElementById("cvTitle"), editor: () => els.cvEditor },
    prompt: { tabLabel: "Prompt", title: document.getElementById("promptTitle"), editor: () => els.promptEditor },
    jobspec: { tabLabel: "Job Spec", title: document.getElementById("jobspecTitle"), editor: () => els.jobspecEditor },
    env: { tabLabel: "Env", title: document.getElementById("envTitle"), editor: () => els.envEditor },
};

const SPLITTER_MIN_LEFT_PX = 360;
const SPLITTER_MIN_RIGHT_PX = 320;

const LS_KEYS = {
    cv: "cvweb.cv",
    prompt: "cvweb.prompt",
    jobspec: "cvweb.jobspec",
    env: "cvweb.env",
};

function setStatus(message, isError = false) {
    els.statusText.textContent = message;
    els.statusText.style.color = isError ? "#b42318" : "#1f1f1f";
}

function setRunning(running) {
    state.isRunning = running;
    [
        els.runFormatBtn,
        els.runFullBtn,
        ...els.fileLoadButtons,
        ...els.fileSaveButtons,
    ].forEach((btn) => {
        if (!btn) {
            return;
        }
        btn.disabled = running;
    });
}

function currentFiles() {
    return {
        cv: els.cvEditor.value,
        prompt: els.promptEditor.value,
        jobspec: els.jobspecEditor.value,
        env: els.envEditor.value,
    };
}

function syncDirtyIndicators() {
    Object.entries(EDITABLE_FILES).forEach(([key, cfg]) => {
        const editor = cfg.editor();
        const diskValue = state.diskFiles[key] || "";
        const isDirty = editor.value !== diskValue;
        const suffix = isDirty ? "*" : "";

        const tabLabelEl = els.tabLabels.find((el) => el.dataset.labelFor === key);
        if (tabLabelEl) {
            tabLabelEl.textContent = `${cfg.tabLabel}${suffix}`;
        }
        if (cfg.title) {
            cfg.title.textContent = `${cfg.tabLabel}${suffix}`;
        }
    });
}

function writeDraftToLocalStorage() {
    const files = currentFiles();
    localStorage.setItem(LS_KEYS.cv, files.cv);
    localStorage.setItem(LS_KEYS.prompt, files.prompt);
    localStorage.setItem(LS_KEYS.jobspec, files.jobspec);
    localStorage.setItem(LS_KEYS.env, files.env);
}

function hasLocalDraft() {
    return [LS_KEYS.cv, LS_KEYS.prompt, LS_KEYS.jobspec, LS_KEYS.env].some(
        (key) => localStorage.getItem(key) !== null,
    );
}

function loadLocalDraft(diskFiles = {}) {
    const cv = localStorage.getItem(LS_KEYS.cv);
    const prompt = localStorage.getItem(LS_KEYS.prompt);
    const jobspec = localStorage.getItem(LS_KEYS.jobspec);
    const env = localStorage.getItem(LS_KEYS.env);

    if (cv !== null) {
        els.cvEditor.value = cv;
    }
    if (prompt !== null) {
        els.promptEditor.value = prompt;
    }
    if (jobspec !== null) {
        els.jobspecEditor.value = jobspec;
    }
    if (env !== null) {
        const diskEnv = diskFiles.env || "";
        if (env === "" && diskEnv.trim() !== "") {
            els.envEditor.value = diskEnv;
        } else {
            els.envEditor.value = env;
        }
    }
}

function applyFilesToEditors(files) {
    els.cvEditor.value = files.cv || "";
    els.promptEditor.value = files.prompt || "";
    els.jobspecEditor.value = files.jobspec || "";
    els.envEditor.value = files.env || "";
}

function updateDiskSnapshot(files) {
    state.diskFiles = {
        cv: files.cv || "",
        prompt: files.prompt || "",
        jobspec: files.jobspec || "",
        env: files.env || "",
    };
    syncDirtyIndicators();
}

async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }

    return response.json();
}

async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }
    return response.text();
}

function updatePreviewCacheBuster() {
    const ts = Date.now();
    els.pdfPreview.src = `/output/tailored_dev.pdf?ts=${ts}`;
}

function summarizeRun(run) {
    if (!run || typeof run !== "object") {
        return "No run output yet.";
    }

    const summary = [
        `Kind: ${run.kind}`,
        `Exit: ${run.exitCode}`,
        `Elapsed: ${run.elapsedSeconds}s`,
        "",
    ];

    if (run.output) {
        summary.push(run.output);
    } else {
        summary.push("(No process output)");
    }

    return summary.join("\n");
}

async function refreshTailoredOutput() {
    if (!els.tailoredViewer) {
        return;
    }

    try {
        const text = await fetchText(`/output/tailored.md?ts=${Date.now()}`);
        els.tailoredViewer.value = text;
    } catch (_err) {
        els.tailoredViewer.value = "tailored.md not found yet. Run full pipeline first.";
    }
}

function bindAutosave() {
    let timer = null;
    const schedule = () => {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            writeDraftToLocalStorage();
            setStatus("Draft saved to browser storage.");
        }, 300);
    };

    [els.cvEditor, els.promptEditor, els.jobspecEditor, els.envEditor].forEach((editor) => {
        editor.addEventListener("input", schedule);
        editor.addEventListener("input", syncDirtyIndicators);
    });
}

async function saveSingleFile(fileKey) {
    if (!EDITABLE_FILES[fileKey]) {
        return;
    }

    const payload = { files: { [fileKey]: currentFiles()[fileKey] } };
    setRunning(true);
    setStatus(`Saving ${EDITABLE_FILES[fileKey].tabLabel}...`);
    try {
        writeDraftToLocalStorage();
        const result = await api("/api/save", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        const files = (result.state && result.state.files) || {};
        if (Object.keys(files).length > 0) {
            updateDiskSnapshot(files);
            applyFilesToEditors(files);
        }
        setStatus(`${EDITABLE_FILES[fileKey].tabLabel} saved.`);
    } catch (err) {
        setStatus(`Save failed: ${err.message}`, true);
    } finally {
        setRunning(false);
    }
}

async function loadSingleFile(fileKey) {
    if (!EDITABLE_FILES[fileKey]) {
        return;
    }

    setRunning(true);
    setStatus(`Loading ${EDITABLE_FILES[fileKey].tabLabel} from disk...`);
    try {
        const result = await api("/api/state");
        const files = result.files || {};
        const editor = EDITABLE_FILES[fileKey].editor();
        editor.value = files[fileKey] || "";
        writeDraftToLocalStorage();
        updateDiskSnapshot(files);
        setStatus(`${EDITABLE_FILES[fileKey].tabLabel} loaded from disk.`);
    } catch (err) {
        setStatus(`Load failed: ${err.message}`, true);
    } finally {
        setRunning(false);
    }
}

async function refreshLogs() {
    try {
        const payload = await api("/api/logs");
        const logs = payload.logs || [];

        els.logSelect.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select debug log...";
        els.logSelect.appendChild(placeholder);

        logs.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.name;
            const when = new Date(item.mtime * 1000).toLocaleString();
            option.textContent = `${item.name} (${when})`;
            els.logSelect.appendChild(option);
        });

        if (payload.lastRun) {
            els.runLogOutput.textContent = summarizeRun(payload.lastRun);
        }
    } catch (err) {
        els.debugLogOutput.textContent = `Unable to load logs: ${err.message}`;
    }
}

async function loadSelectedDebugLog() {
    const name = els.logSelect.value;
    if (!name) {
        els.debugLogOutput.textContent = "Select a debug log to view its content.";
        return;
    }

    try {
        const payload = await api(`/api/logs/content?name=${encodeURIComponent(name)}`);
        els.debugLogOutput.textContent = payload.content || "(Empty log file)";
    } catch (err) {
        els.debugLogOutput.textContent = `Unable to load log file: ${err.message}`;
    }
}

async function saveToDisk() {
    setRunning(true);
    setStatus("Saving files...");
    try {
        writeDraftToLocalStorage();
        await api("/api/save", {
            method: "POST",
            body: JSON.stringify({ files: currentFiles() }),
        });
        setStatus("Saved to disk.");
    } catch (err) {
        setStatus(`Save failed: ${err.message}`, true);
    } finally {
        setRunning(false);
    }
}

async function runPipeline(kind) {
    setRunning(true);
    setStatus(kind === "full" ? "Running full pipeline..." : "Running formatting only...");

    try {
        writeDraftToLocalStorage();
        const payload = await api(kind === "full" ? "/api/run/full" : "/api/run/format", {
            method: "POST",
            body: JSON.stringify({ files: currentFiles() }),
        });

        const run = payload.run || null;
        if (payload.state && payload.state.files) {
            updateDiskSnapshot(payload.state.files);
        }
        els.runLogOutput.textContent = summarizeRun(run);
        updatePreviewCacheBuster();
        await refreshTailoredOutput();
        await refreshLogs();

        if (run && run.success) {
            setStatus(`Run complete (${run.elapsedSeconds}s).`);
        } else {
            setStatus("Run failed. Open logs for details.", true);
        }
    } catch (err) {
        setStatus(`Run failed: ${err.message}`, true);
        els.runLogOutput.textContent = err.stack || err.message;
    } finally {
        setRunning(false);
    }
}

async function reloadFromDisk() {
    setRunning(true);
    setStatus("Reloading from disk...");

    try {
        const payload = await api("/api/state");
        applyFilesToEditors(payload.files || {});
        updateDiskSnapshot(payload.files || {});
        writeDraftToLocalStorage();
        updatePreviewCacheBuster();
        await refreshTailoredOutput();
        setStatus("Reloaded from disk.");
    } catch (err) {
        setStatus(`Reload failed: ${err.message}`, true);
    } finally {
        setRunning(false);
    }
}

function setActiveTab(tabName) {
    if (!els.tabPanels[tabName]) {
        return;
    }

    state.activeTab = tabName;
    els.tabButtons.forEach((button) => {
        const isActive = button.dataset.tab === tabName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    Object.entries(els.tabPanels).forEach(([name, panel]) => {
        panel.classList.toggle("active", name === tabName);
    });

    if (tabName === "logs") {
        refreshLogs();
    } else if (tabName === "tailored") {
        refreshTailoredOutput();
    }
}

function setActiveLogTab(tabName) {
    if (!els.logPanels[tabName]) {
        return;
    }

    state.activeLogTab = tabName;
    els.logTabButtons.forEach((button) => {
        const isActive = button.dataset.logTab === tabName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    Object.entries(els.logPanels).forEach(([name, panel]) => {
        panel.classList.toggle("active", name === tabName);
    });
}

function updateSplitterPosition(clientX) {
    if (!els.layout) {
        return;
    }

    const rect = els.layout.getBoundingClientRect();
    const maxLeft = rect.width - SPLITTER_MIN_RIGHT_PX;
    const next = Math.min(Math.max(clientX - rect.left, SPLITTER_MIN_LEFT_PX), maxLeft);
    const pct = (next / rect.width) * 100;
    els.layout.style.setProperty("--left-pane-width", `${pct}%`);
}

function onSplitterPointerDown(event) {
    if (!els.paneSplitter || window.matchMedia("(max-width: 1100px)").matches) {
        return;
    }

    state.isDraggingSplitter = true;
    els.paneSplitter.classList.add("dragging");
    els.paneSplitter.setPointerCapture(event.pointerId);
    updateSplitterPosition(event.clientX);
}

function onSplitterPointerMove(event) {
    if (!state.isDraggingSplitter) {
        return;
    }
    updateSplitterPosition(event.clientX);
}

function onSplitterPointerUp(event) {
    if (!state.isDraggingSplitter || !els.paneSplitter) {
        return;
    }

    state.isDraggingSplitter = false;
    els.paneSplitter.classList.remove("dragging");
    try {
        els.paneSplitter.releasePointerCapture(event.pointerId);
    } catch (_err) {
        // Ignore capture release errors when pointer is no longer active.
    }
}

async function initialize() {
    setStatus("Loading editor state...");
    try {
        const payload = await api("/api/state");
        applyFilesToEditors(payload.files || {});
        updateDiskSnapshot(payload.files || {});

        if (hasLocalDraft()) {
            loadLocalDraft(payload.files || {});
            setStatus("Loaded browser draft. Use per-tab Save to write to disk.");
            syncDirtyIndicators();
        } else {
            writeDraftToLocalStorage();
            setStatus("Loaded from disk.");
            syncDirtyIndicators();
        }

        if (payload.lastRun) {
            els.runLogOutput.textContent = summarizeRun(payload.lastRun);
        }

        updatePreviewCacheBuster();
        await refreshTailoredOutput();
    } catch (err) {
        setStatus(`Initialization failed: ${err.message}`, true);
    }
}

els.runFormatBtn.addEventListener("click", () => runPipeline("format"));
els.runFullBtn.addEventListener("click", () => runPipeline("full"));
els.refreshLogsBtn.addEventListener("click", refreshLogs);
els.logSelect.addEventListener("change", loadSelectedDebugLog);
els.tabButtons.forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});
els.logTabButtons.forEach((button) => {
    button.addEventListener("click", () => setActiveLogTab(button.dataset.logTab));
});
els.fileSaveButtons.forEach((button) => {
    button.addEventListener("click", () => saveSingleFile(button.dataset.file));
});
els.fileLoadButtons.forEach((button) => {
    button.addEventListener("click", () => loadSingleFile(button.dataset.file));
});
if (els.paneSplitter) {
    els.paneSplitter.addEventListener("pointerdown", onSplitterPointerDown);
    window.addEventListener("pointermove", onSplitterPointerMove);
    window.addEventListener("pointerup", onSplitterPointerUp);
    window.addEventListener("pointercancel", onSplitterPointerUp);
}

bindAutosave();
initialize();
