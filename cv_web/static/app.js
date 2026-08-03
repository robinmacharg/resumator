const state = {
    isRunning: false,
    isResearchRunning: false,
    activeTab: "cv",
    activeLogTab: "run",
    isDraggingSplitter: false,
    diskFiles: {},
    runStatusTimerId: null,
    runStatusStartMs: 0,
    runStatusMessage: "",
};

const els = {
    statusText: document.getElementById("statusText"),
    cvEditor: document.getElementById("cvEditor"),
    promptEditor: document.getElementById("promptEditor"),
    researchPromptEditor: document.getElementById("researchPromptEditor"),
    researchCompanyInput: document.getElementById("researchCompanyInput"),
    researchUrlsInput: document.getElementById("researchUrlsInput"),
    researchDryRunCheckbox: document.getElementById("researchDryRunCheckbox"),
    runResearchBtn: document.getElementById("runResearchBtn"),
    resetResearchPromptBtn: document.getElementById("resetResearchPromptBtn"),
    copyResearchOutputBtn: document.getElementById("copyResearchOutputBtn"),
    researchStatusText: document.getElementById("researchStatusText"),
    researchOutput: document.getElementById("researchOutput"),
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
        research: document.getElementById("tab-research"),
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
    prompt: {
        tabLabel: "CV Prompt",
        title: document.getElementById("promptTitle"),
        editor: () => els.promptEditor,
    },
    research_prompt: {
        tabLabel: "Research Role",
        title: document.getElementById("researchPromptTitle"),
        editor: () => els.researchPromptEditor,
    },
    jobspec: {
        tabLabel: "Job Spec",
        title: document.getElementById("jobspecTitle"),
        editor: () => els.jobspecEditor,
    },
    env: {
        tabLabel: "Env",
        title: document.getElementById("envTitle"),
        editor: () => els.envEditor,
    },
};

const SPLITTER_MIN_LEFT_PX = 360;
const SPLITTER_MIN_RIGHT_PX = 320;

const LS_KEYS = {
    cv: "cvweb.cv",
    prompt: "cvweb.prompt",
    research_prompt: "cvweb.research_prompt",
    research_company: "cvweb.research.company",
    research_urls: "cvweb.research.urls",
    jobspec: "cvweb.jobspec",
    env: "cvweb.env",
};

function setStatus(message, isError = false) {
    els.statusText.textContent = message;
    els.statusText.style.color = isError ? "#b42318" : "#1f1f1f";
}

function startRunStatusTimer(message) {
    stopRunStatusTimer();
    state.runStatusMessage = message;
    state.runStatusStartMs = Date.now();

    const render = () => {
        const elapsedSeconds = Math.floor((Date.now() - state.runStatusStartMs) / 1000);
        setStatus(`${state.runStatusMessage} [${elapsedSeconds}s]`);
    };

    render();
    state.runStatusTimerId = window.setInterval(render, 1000);
}

function stopRunStatusTimer() {
    if (state.runStatusTimerId !== null) {
        clearInterval(state.runStatusTimerId);
        state.runStatusTimerId = null;
    }
    state.runStatusStartMs = 0;
    state.runStatusMessage = "";
}

function applyControlDisabledState() {
    const disabled = state.isRunning || state.isResearchRunning;
    [
        els.runFormatBtn,
        els.runFullBtn,
        ...els.fileLoadButtons,
        ...els.fileSaveButtons,
        els.runResearchBtn,
        els.resetResearchPromptBtn,
        els.copyResearchOutputBtn,
        els.researchCompanyInput,
        els.researchUrlsInput,
        els.researchDryRunCheckbox,
    ].forEach((el) => {
        if (!el) {
            return;
        }
        el.disabled = disabled;
    });
}

function setRunning(running) {
    state.isRunning = running;
    applyControlDisabledState();
}

function setResearchRunning(running) {
    state.isResearchRunning = running;
    applyControlDisabledState();
}

function currentFiles() {
    return {
        cv: els.cvEditor.value,
        prompt: els.promptEditor.value,
        research_prompt: els.researchPromptEditor.value,
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
    localStorage.setItem(LS_KEYS.research_prompt, files.research_prompt);
    localStorage.setItem(LS_KEYS.research_company, els.researchCompanyInput.value || "");
    localStorage.setItem(LS_KEYS.research_urls, els.researchUrlsInput.value || "");
    localStorage.setItem(LS_KEYS.jobspec, files.jobspec);
    localStorage.setItem(LS_KEYS.env, files.env);
}

function hasLocalDraft() {
    return [
        LS_KEYS.cv,
        LS_KEYS.prompt,
        LS_KEYS.research_prompt,
        LS_KEYS.research_company,
        LS_KEYS.research_urls,
        LS_KEYS.jobspec,
        LS_KEYS.env,
    ].some((key) => localStorage.getItem(key) !== null);
}

function loadLocalDraft(diskFiles = {}) {
    const cv = localStorage.getItem(LS_KEYS.cv);
    const prompt = localStorage.getItem(LS_KEYS.prompt);
    const researchPrompt = localStorage.getItem(LS_KEYS.research_prompt);
    const researchCompany = localStorage.getItem(LS_KEYS.research_company);
    const researchUrls = localStorage.getItem(LS_KEYS.research_urls);
    const jobspec = localStorage.getItem(LS_KEYS.jobspec);
    const env = localStorage.getItem(LS_KEYS.env);

    if (cv !== null) {
        els.cvEditor.value = cv;
    }
    if (prompt !== null) {
        els.promptEditor.value = prompt;
    }
    if (researchPrompt !== null) {
        els.researchPromptEditor.value = researchPrompt;
    }
    if (researchCompany !== null) {
        els.researchCompanyInput.value = researchCompany;
    }
    if (researchUrls !== null) {
        els.researchUrlsInput.value = researchUrls;
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
    els.researchPromptEditor.value = files.research_prompt || "";
    els.jobspecEditor.value = files.jobspec || "";
    els.envEditor.value = files.env || "";
}

function updateDiskSnapshot(files) {
    state.diskFiles = {
        cv: files.cv || "",
        prompt: files.prompt || "",
        research_prompt: files.research_prompt || "",
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

function setRunLogOutput(text) {
    els.runLogOutput.textContent = text;
    els.runLogOutput.scrollTop = els.runLogOutput.scrollHeight;
}

function setResearchStatus(message, isError = false) {
    if (!els.researchStatusText) {
        return;
    }
    els.researchStatusText.textContent = message;
    els.researchStatusText.style.color = isError ? "#b42318" : "#57534e";
}

function setResearchOutput(text) {
    if (!els.researchOutput) {
        return;
    }
    els.researchOutput.textContent = text;
    els.researchOutput.scrollTop = els.researchOutput.scrollHeight;
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function summarizeRun(run) {
    if (!run || typeof run !== "object") {
        return "No run output yet.";
    }

    const isRunning = Boolean(run.running);
    const exitDisplay =
        run.exitCode === null || run.exitCode === undefined ? "running" : run.exitCode;
    const elapsedDisplay =
        run.elapsedSeconds === null || run.elapsedSeconds === undefined
            ? "-"
            : `${run.elapsedSeconds}s`;

    const summary = [
        `Kind: ${run.kind}`,
        `Exit: ${exitDisplay}`,
        `Elapsed: ${elapsedDisplay}`,
        `Status: ${isRunning ? "running" : run.success ? "success" : "failed"}`,
        "",
    ];

    if (run.output) {
        summary.push(run.output);
    } else {
        summary.push("(No process output)");
    }

    return summary.join("\n");
}

function parseResearchUrlsInput(rawText) {
    const seen = new Set();
    const urls = [];
    (rawText || "").split(/\r?\n/).forEach((line) => {
        const cleaned = line.trim();
        if (!cleaned || cleaned.startsWith("#") || seen.has(cleaned)) {
            return;
        }
        seen.add(cleaned);
        urls.push(cleaned);
    });
    return urls;
}

function summarizeResearchOutput(run) {
    if (!run) {
        return "No research run output yet.";
    }
    const status = run.running ? "running" : run.success ? "success" : "failed";
    const elapsed =
        run.elapsedSeconds === null || run.elapsedSeconds === undefined
            ? "-"
            : `${run.elapsedSeconds}s`;
    const exit = run.exitCode === null || run.exitCode === undefined ? "running" : run.exitCode;

    const lines = [
        `Company: ${run.companyName || "(unknown)"}`,
        `Status: ${status}`,
        `Exit: ${exit}`,
        `Elapsed: ${elapsed}`,
        `Dry Run: ${run.dryRun ? "yes" : "no"}`,
        "",
        run.output || "(No process output)",
    ];
    return lines.join("\n");
}

function renderResearchState(payload) {
    if (!payload || typeof payload !== "object") {
        return;
    }

    if (typeof payload.companyName === "string") {
        els.researchCompanyInput.value = payload.companyName;
    }

    if (Array.isArray(payload.urls)) {
        els.researchUrlsInput.value = payload.urls.join("\n");
    }

    const output = payload.output || {};
    if (typeof output.markdown === "string" && output.markdown.trim()) {
        setResearchOutput(output.markdown);
    } else if (typeof output.json === "string" && output.json.trim()) {
        setResearchOutput(output.json);
    }

    if (payload.lastRun) {
        setResearchOutput(summarizeResearchOutput(payload.lastRun));
    }
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

    [
        els.cvEditor,
        els.promptEditor,
        els.researchPromptEditor,
        els.jobspecEditor,
        els.envEditor,
    ].forEach((editor) => {
        editor.addEventListener("input", schedule);
        editor.addEventListener("input", syncDirtyIndicators);
    });

    [els.researchCompanyInput, els.researchUrlsInput].forEach((inputEl) => {
        if (!inputEl) {
            return;
        }
        inputEl.addEventListener("input", schedule);
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
            setRunLogOutput(summarizeRun(payload.lastRun));
        }
    } catch (err) {
        els.debugLogOutput.textContent = `Unable to load logs: ${err.message}`;
    }
}

async function fetchRunStatus() {
    return api("/api/run/status");
}

async function fetchResearchStatus() {
    return api("/api/research/status");
}

async function waitForRunCompletion() {
    while (true) {
        const status = await fetchRunStatus();
        const run = status.run || null;
        if (run) {
            setRunLogOutput(summarizeRun(run));
        }

        if (!status.running) {
            return run;
        }

        await sleep(1000);
    }
}

async function waitForResearchCompletion() {
    while (true) {
        const status = await fetchResearchStatus();
        const run = status.run || null;
        if (run) {
            setResearchOutput(summarizeResearchOutput(run));
            if (status.running) {
                setResearchStatus(`Research running (${run.elapsedSeconds || 0}s)...`);
            }
        }

        if (!status.running) {
            return run;
        }

        await sleep(1000);
    }
}

async function runResearch() {
    const companyName = (els.researchCompanyInput.value || "").trim();
    if (!companyName) {
        setStatus("Company name is required for research run.", true);
        setResearchStatus("Company name is required.", true);
        return;
    }

    const researchPrompt = (els.researchPromptEditor.value || "").trim();
    if (!researchPrompt) {
        setStatus("Research prompt is empty. Reset prompt or add content before running.", true);
        setResearchStatus("Research prompt is empty.", true);
        setResearchOutput(
            "Research prompt is empty. Use 'Reset Prompt to Default' or enter a custom prompt.",
        );
        return;
    }

    const urls = parseResearchUrlsInput(els.researchUrlsInput.value || "");

    setResearchRunning(true);
    setResearchStatus("Starting research run...");
    setResearchOutput("Starting research run...");

    try {
        writeDraftToLocalStorage();
        const kickoff = await api("/api/research/run", {
            method: "POST",
            body: JSON.stringify({
                files: currentFiles(),
                companyName,
                urls,
                dryRun: Boolean(els.researchDryRunCheckbox.checked),
            }),
        });

        if (kickoff.run) {
            setResearchOutput(summarizeResearchOutput(kickoff.run));
        }

        const run = await waitForResearchCompletion();
        if (run && run.success) {
            setResearchStatus(`Research complete (${run.elapsedSeconds}s).`);
            setStatus("Research run complete.");
        } else {
            setResearchStatus("Research run failed.", true);
            setStatus("Research run failed. See Research Output.", true);
        }

        const refreshed = await api("/api/research/state");
        renderResearchState(refreshed);
    } catch (err) {
        setResearchStatus(`Research run failed: ${err.message}`, true);
        setResearchOutput(err.stack || err.message);
        setStatus(`Research run failed: ${err.message}`, true);
    } finally {
        setResearchRunning(false);
    }
}

async function resetResearchPrompt() {
    const confirmed = window.confirm(
        "Reset research prompt to default? This will overwrite the current research prompt file.",
    );
    if (!confirmed) {
        return;
    }

    setResearchRunning(true);
    setResearchStatus("Resetting prompt to default...");

    try {
        await api("/api/research/reset-prompt", {
            method: "POST",
            body: JSON.stringify({}),
        });

        const disk = await api("/api/state");
        const files = disk.files || {};
        if (typeof files.research_prompt === "string") {
            els.researchPromptEditor.value = files.research_prompt;
            updateDiskSnapshot(files);
            writeDraftToLocalStorage();
        }

        const researchState = await api("/api/research/state");
        renderResearchState(researchState);
        setResearchStatus("Prompt reset to default.");
        setStatus("Research prompt reset from default file.");
    } catch (err) {
        setResearchStatus(`Reset failed: ${err.message}`, true);
        setStatus(`Research prompt reset failed: ${err.message}`, true);
    } finally {
        setResearchRunning(false);
    }
}

async function copyResearchOutputToClipboard() {
    const text = (
        els.researchOutput && els.researchOutput.textContent ? els.researchOutput.textContent : ""
    ).trim();
    if (!text) {
        setResearchStatus("No research output to copy.", true);
        return;
    }

    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.position = "absolute";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
        }
        setResearchStatus("Research output copied to clipboard.");
    } catch (err) {
        setResearchStatus(`Copy failed: ${err.message}`, true);
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
    startRunStatusTimer(
        kind === "full" ? "Running full pipeline..." : "Running formatting only...",
    );
    setRunLogOutput("Starting run...");

    try {
        writeDraftToLocalStorage();
        const kickoff = await api(kind === "full" ? "/api/run/full" : "/api/run/format", {
            method: "POST",
            body: JSON.stringify({ files: currentFiles() }),
        });
        if (kickoff.run) {
            setRunLogOutput(summarizeRun(kickoff.run));
        }

        const run = await waitForRunCompletion();

        const refreshedState = await api("/api/state");
        if (refreshedState.files) {
            updateDiskSnapshot(refreshedState.files);
        }

        updatePreviewCacheBuster();
        await refreshTailoredOutput();
        await refreshLogs();

        stopRunStatusTimer();
        if (run && run.success) {
            setStatus(`Run complete (${run.elapsedSeconds}s).`);
        } else {
            setStatus("Run failed. Open logs for details.", true);
        }
    } catch (err) {
        stopRunStatusTimer();
        setStatus(`Run failed: ${err.message}`, true);
        setRunLogOutput(err.stack || err.message);
    } finally {
        stopRunStatusTimer();
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
        const researchPayload = await api("/api/research/state");
        renderResearchState(researchPayload);

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
            setRunLogOutput(summarizeRun(payload.lastRun));
        }

        const currentResearch = await fetchResearchStatus();
        if (currentResearch.run) {
            setResearchOutput(summarizeResearchOutput(currentResearch.run));
            if (currentResearch.running) {
                setResearchStatus("Research run in progress...");
                setResearchRunning(true);
                waitForResearchCompletion()
                    .then((run) => {
                        if (run && run.success) {
                            setResearchStatus(`Research complete (${run.elapsedSeconds}s).`);
                        } else {
                            setResearchStatus("Research run failed.", true);
                        }
                    })
                    .catch((err) => {
                        setResearchStatus(`Research status polling failed: ${err.message}`, true);
                    })
                    .finally(() => {
                        setResearchRunning(false);
                    });
            } else {
                setResearchStatus(
                    currentResearch.run.success ? "Last run succeeded." : "Last run failed.",
                );
            }
        } else {
            setResearchStatus("Idle.");
        }

        updatePreviewCacheBuster();
        await refreshTailoredOutput();
    } catch (err) {
        setStatus(`Initialization failed: ${err.message}`, true);
    }
}

els.runFormatBtn.addEventListener("click", () => runPipeline("format"));
els.runFullBtn.addEventListener("click", () => runPipeline("full"));
if (els.runResearchBtn) {
    els.runResearchBtn.addEventListener("click", runResearch);
}
if (els.resetResearchPromptBtn) {
    els.resetResearchPromptBtn.addEventListener("click", resetResearchPrompt);
}
if (els.copyResearchOutputBtn) {
    els.copyResearchOutputBtn.addEventListener("click", copyResearchOutputToClipboard);
}
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
