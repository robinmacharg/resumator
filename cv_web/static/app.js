import { api, fetchText } from "./js/api-client.js";
import { createCvPipelineFeature } from "./js/cv-pipeline-feature.js";
import { createLogsFeature } from "./js/logs-feature.js";
import { createPdfPreviewFeature } from "./js/pdf-preview-feature.js";
import { createProviderModelFeature } from "./js/provider-model-feature.js";
import { createResearchFeature } from "./js/research-feature.js";
import { createUiLayoutFeature } from "./js/ui-layout-feature.js";
import { formatCommandForDisplay, formatTimestampToSecond, sleep } from "./js/app-utils.js";

const state = {
    isRunning: false,
    isResearchRunning: false,
    selectedProvider: "gemini",
    selectedModel: "",
    defaultProvider: "gemini",
    modelsByProvider: {},
    activeTab: "cv",
    activeCvTab: "cv",
    activeResearchInputTab: "query",
    activeLogTab: "run",
    activeResearchOutputTab: "console",
    isDraggingSplitter: false,
    isDraggingResearchSplitter: false,
    activeResearchSplitter: null,
    researchSectionRatios: [1 / 3, 1 / 3, 1 / 3],
    diskFiles: {},
    runStatusTimerId: null,
    runStatusStartMs: 0,
    runStatusMessage: "",
};

const els = {
    statusText: document.getElementById("statusText"),
    providerSelect: document.getElementById("providerSelect"),
    modelSelect: document.getElementById("modelSelect"),
    cvEditor: document.getElementById("cvEditor"),
    promptEditor: document.getElementById("promptEditor"),
    researchPromptEditor: document.getElementById("researchPromptEditor"),
    researchJobspecEditor: document.getElementById("researchJobspecEditor"),
    researchCvEditor: document.getElementById("researchCvEditor"),
    researchCompanyInput: document.getElementById("researchCompanyInput"),
    researchUrlsInput: document.getElementById("researchUrlsInput"),
    researchDryRunCheckbox: document.getElementById("researchDryRunCheckbox"),
    runResearchBtn: document.getElementById("runResearchBtn"),
    formatResearchBtn: document.getElementById("formatResearchBtn"),
    resetResearchPromptBtn: document.getElementById("resetResearchPromptBtn"),
    copyResearchOutputBtn: document.getElementById("copyResearchOutputBtn"),
    researchStatusText: document.getElementById("researchStatusText"),
    researchOutput: document.getElementById("researchOutput"),
    researchBuiltQueryOutput: document.getElementById("researchBuiltQueryOutput"),
    researchCommandOutput: document.getElementById("researchCommandOutput"),
    researchAutoscrollIndicator: document.getElementById("researchAutoscrollIndicator"),
    jobspecEditor: document.getElementById("jobspecEditor"),
    envEditor: document.getElementById("envEditor"),
    tailoredViewer: document.getElementById("tailoredViewer"),
    runFormatBtn: document.getElementById("runFormatBtn"),
    runFullBtn: document.getElementById("runFullBtn"),
    restartServerBtn: document.getElementById("restartServerBtn"),
    runLogOutput: document.getElementById("runLogOutput"),
    debugLogOutput: document.getElementById("debugLogOutput"),
    refreshLogsBtn: document.getElementById("refreshLogsBtn"),
    logsAutoscrollIndicator: document.getElementById("logsAutoscrollIndicator"),
    logSelect: document.getElementById("logSelect"),
    pdfPreview: document.getElementById("pdfPreview"),
    pdfPlaceholder: document.getElementById("pdfPlaceholder"),
    pdfPreviewTitle: document.getElementById("pdfPreviewTitle"),
    pdfPreviewOpenLink: document.getElementById("pdfPreviewOpenLink"),
    layout: document.querySelector(".layout"),
    paneSplitter: document.getElementById("paneSplitter"),
    tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
    tabLabels: Array.from(document.querySelectorAll(".tab-label")),
    fileLoadButtons: Array.from(document.querySelectorAll(".file-load-btn")),
    fileSaveButtons: Array.from(document.querySelectorAll(".file-save-btn")),
    tabPanels: {
        cv: document.getElementById("panel-top-cv"),
        research: document.getElementById("tab-research"),
        logs: document.getElementById("tab-logs"),
    },
    researchSplitters: Array.from(document.querySelectorAll(".research-section-splitter")),
    cvTabButtons: Array.from(document.querySelectorAll(".cv-subtab-btn")),
    researchInputTabButtons: Array.from(document.querySelectorAll(".research-input-tab-btn")),
    cvTabPanels: {
        cv: document.getElementById("tab-cv"),
        prompt: document.getElementById("tab-prompt"),
        jobspec: document.getElementById("tab-jobspec"),
        env: document.getElementById("tab-env"),
        tailored: document.getElementById("tab-tailored"),
    },
    researchInputPanels: {
        query: document.getElementById("research-input-panel-query"),
        jobspec: document.getElementById("research-input-panel-jobspec"),
        cv: document.getElementById("research-input-panel-cv"),
    },
    logTabButtons: Array.from(document.querySelectorAll(".log-tab-btn")),
    researchOutputTabButtons: Array.from(document.querySelectorAll(".research-output-tab-btn")),
    logPanels: {
        run: document.getElementById("log-panel-run"),
        debug: document.getElementById("log-panel-debug"),
    },
    researchOutputPanels: {
        console: document.getElementById("research-output-panel-console"),
        built_query: document.getElementById("research-output-panel-built-query"),
        command: document.getElementById("research-output-panel-command"),
    },
};

const previewFeature = createPdfPreviewFeature({
    els,
    getActivePreviewKind: () => (state.activeTab === "research" ? "research" : "cv"),
});

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

const LS_KEYS = {
    cv: "cvweb.cv",
    prompt: "cvweb.prompt",
    research_prompt: "cvweb.research_prompt",
    research_company: "cvweb.research.company",
    research_urls: "cvweb.research.urls",
    jobspec: "cvweb.jobspec",
    env: "cvweb.env",
    active_tab: "cvweb.active_tab",
    active_cv_tab: "cvweb.active_cv_tab",
    active_research_input_tab: "cvweb.active_research_input_tab",
    research_section_ratios: "cvweb.research_section_ratios",
    active_log_tab: "cvweb.active_log_tab",
    research_output_tab: "cvweb.research_output_tab",
    selected_provider: "cvweb.selected_provider",
    selected_model: "cvweb.selected_model",
};

const AUTO_SCROLL_BOTTOM_TOLERANCE_PX = 6;
const autoScrollTrackerByEl = new WeakMap();

function getAutoScrollTracker(el) {
    if (!el) {
        return null;
    }
    let tracker = autoScrollTrackerByEl.get(el);
    if (tracker) {
        return tracker;
    }

    tracker = { hasUserScrolled: false, programmaticScrollInProgress: false };
    el.addEventListener("scroll", () => {
        if (tracker.programmaticScrollInProgress) {
            return;
        }
        tracker.hasUserScrolled = true;
        updateAutoScrollIndicators();
    });
    autoScrollTrackerByEl.set(el, tracker);
    return tracker;
}

function isAutoscrollPaused(el) {
    const tracker = getAutoScrollTracker(el);
    return Boolean(tracker && tracker.hasUserScrolled && !isAtBottom(el));
}

function setAutoscrollIndicator(el, paused) {
    if (!el) {
        return;
    }
    const nextText = paused ? "Auto-scroll paused" : "";
    el.textContent = nextText;
    el.classList.toggle("visible", paused);
    el.setAttribute("aria-hidden", paused ? "false" : "true");
}

function getActiveResearchOutputElement() {
    if (state.activeResearchOutputTab === "built_query") {
        return els.researchBuiltQueryOutput;
    }
    if (state.activeResearchOutputTab === "command") {
        return els.researchCommandOutput;
    }
    return els.researchOutput;
}

function getActiveLogElement() {
    if (state.activeLogTab === "debug") {
        return els.debugLogOutput;
    }
    return els.runLogOutput;
}

function updateAutoScrollIndicators() {
    setAutoscrollIndicator(
        els.researchAutoscrollIndicator,
        isAutoscrollPaused(getActiveResearchOutputElement()),
    );
    setAutoscrollIndicator(els.logsAutoscrollIndicator, isAutoscrollPaused(getActiveLogElement()));
}

function isAtBottom(el) {
    if (!el) {
        return true;
    }
    const distanceFromBottom = el.scrollHeight - el.clientHeight - el.scrollTop;
    return distanceFromBottom <= AUTO_SCROLL_BOTTOM_TOLERANCE_PX;
}

function setOutputContentWithSmartAutoscroll(el, text, useValueProperty = false) {
    if (!el) {
        return;
    }

    const tracker = getAutoScrollTracker(el);
    const shouldAutoscroll = !tracker || !tracker.hasUserScrolled || isAtBottom(el);

    if (useValueProperty) {
        el.value = text;
    } else {
        el.textContent = text;
    }

    if (!shouldAutoscroll || !tracker) {
        updateAutoScrollIndicators();
        return;
    }

    tracker.programmaticScrollInProgress = true;
    el.scrollTop = el.scrollHeight;
    requestAnimationFrame(() => {
        tracker.programmaticScrollInProgress = false;
        updateAutoScrollIndicators();
    });
}

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
        els.formatResearchBtn,
        els.resetResearchPromptBtn,
        els.copyResearchOutputBtn,
        els.researchCompanyInput,
        els.researchUrlsInput,
        els.researchDryRunCheckbox,
        els.providerSelect,
        els.modelSelect,
        els.restartServerBtn,
    ].forEach((el) => {
        if (!el) {
            return;
        }
        el.disabled = disabled;
    });

    if (els.runResearchBtn) {
        els.runResearchBtn.disabled = state.isRunning;
    }

    syncResearchPrimaryButton();
}

function setRunning(running) {
    state.isRunning = running;
    applyControlDisabledState();
}

function setResearchRunning(running) {
    state.isResearchRunning = running;
    applyControlDisabledState();
}

function syncResearchPrimaryButton() {
    if (!els.runResearchBtn) {
        return;
    }

    if (state.isResearchRunning) {
        els.runResearchBtn.textContent = "Stop Research";
        els.runResearchBtn.classList.remove("btn-primary");
        els.runResearchBtn.classList.add("btn-danger");
    } else {
        els.runResearchBtn.textContent = "Run Research";
        els.runResearchBtn.classList.remove("btn-danger");
        els.runResearchBtn.classList.add("btn-primary");
    }
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

        const tabLabelEls = els.tabLabels.filter((el) => el.dataset.labelFor === key);
        tabLabelEls.forEach((tabLabelEl) => {
            tabLabelEl.textContent = `${cfg.tabLabel}${suffix}`;
        });
        if (cfg.title) {
            cfg.title.textContent = `${cfg.tabLabel}${suffix}`;
        }
    });
}

function syncResearchMirrorEditorsFromPrimary() {
    if (els.researchJobspecEditor && els.jobspecEditor) {
        els.researchJobspecEditor.value = els.jobspecEditor.value;
    }
    if (els.researchCvEditor && els.cvEditor) {
        els.researchCvEditor.value = els.cvEditor.value;
    }
}

function bindMirroredEditors(primaryEditor, mirrorEditor) {
    if (!primaryEditor || !mirrorEditor) {
        return;
    }

    let syncing = false;

    const syncValues = (source, target) => {
        if (syncing) {
            return;
        }
        if (target.value === source.value) {
            return;
        }

        syncing = true;
        target.value = source.value;
        target.dispatchEvent(new Event("input", { bubbles: true }));
        syncing = false;
    };

    primaryEditor.addEventListener("input", () => syncValues(primaryEditor, mirrorEditor));
    mirrorEditor.addEventListener("input", () => syncValues(mirrorEditor, primaryEditor));
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

    syncResearchMirrorEditorsFromPrimary();
}

function applyFilesToEditors(files) {
    els.cvEditor.value = files.cv || "";
    els.promptEditor.value = files.prompt || "";
    els.researchPromptEditor.value = files.research_prompt || "";
    els.jobspecEditor.value = files.jobspec || "";
    els.envEditor.value = files.env || "";
    syncResearchMirrorEditorsFromPrimary();
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

function setRunLogOutput(text) {
    setOutputContentWithSmartAutoscroll(els.runLogOutput, text);
}

function setDebugLogOutput(text) {
    setOutputContentWithSmartAutoscroll(els.debugLogOutput, text);
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
    setOutputContentWithSmartAutoscroll(els.researchOutput, text);
}

function setResearchBuiltQueryOutput(text) {
    if (!els.researchBuiltQueryOutput) {
        return;
    }
    setOutputContentWithSmartAutoscroll(els.researchBuiltQueryOutput, text);
}

function setResearchCommandOutput(command) {
    if (!els.researchCommandOutput) {
        return;
    }
    const rendered = Array.isArray(command)
        ? formatCommandForDisplay(command)
        : String(command || "");
    setOutputContentWithSmartAutoscroll(
        els.researchCommandOutput,
        rendered || "No command yet. Run Research first.",
        true,
    );
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

function summarizeResearchOutput(run) {
    if (!run) {
        return "No research run output yet.";
    }
    const status = run.running
        ? "running"
        : run.stoppedByUser
          ? "stopped"
          : run.success
            ? "success"
            : "failed";
    const elapsed =
        run.elapsedSeconds === null || run.elapsedSeconds === undefined
            ? "-"
            : `${run.elapsedSeconds}s`;
    const exit = run.exitCode === null || run.exitCode === undefined ? "running" : run.exitCode;

    const operation = run.kind === "research_format" ? "format" : "research";
    const company = run.kind === "research_format" ? "(n/a)" : run.companyName || "(unknown)";

    const lines = [
        `Operation: ${operation}`,
        `Company: ${company}`,
        `Status: ${status}`,
        `Exit: ${exit}`,
        `Elapsed: ${elapsed}`,
        `Dry Run: ${run.dryRun ? "yes" : "no"}`,
        run.autoFormatPdf ? "Auto Format PDF: enabled" : "Auto Format PDF: disabled",
        run.formatAttempted === true
            ? `Format Exit: ${run.formatExitCode === null || run.formatExitCode === undefined ? "-" : run.formatExitCode}`
            : null,
        run.formatAttempted === true
            ? `Format Status: ${run.formatSuccess ? "success" : "failed"}`
            : null,
        run.success
            ? `Generated At: ${formatTimestampToSecond(run.finishedAt || run.startedAt)}`
            : null,
        "",
        run.output || "(No process output)",
    ].filter((line) => line !== null);
    return lines.join("\n");
}

function renderResearchState(payload) {
    if (!payload || typeof payload !== "object") {
        return;
    }

    previewFeature.applyResearchOutputState(payload);

    if (typeof payload.companyName === "string") {
        els.researchCompanyInput.value = payload.companyName;
    }

    if (Array.isArray(payload.urls)) {
        els.researchUrlsInput.value = payload.urls.join("\n");
    }

    const output = payload.output || {};
    if (typeof output.builtPrompt === "string" && output.builtPrompt.trim()) {
        setResearchBuiltQueryOutput(output.builtPrompt);
    } else {
        setResearchBuiltQueryOutput("No built query yet. Run Research first.");
    }

    if (typeof output.markdown === "string" && output.markdown.trim()) {
        setResearchOutput(output.markdown);
    } else if (typeof output.json === "string" && output.json.trim()) {
        setResearchOutput(output.json);
    }

    if (payload.lastRun) {
        setResearchOutput(summarizeResearchOutput(payload.lastRun));
        setResearchCommandOutput(payload.lastRun.command || []);
    } else {
        setResearchCommandOutput([]);
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
        els.tailoredViewer.value = "output/tailored.md not found yet. Run full pipeline first.";
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
        els.researchJobspecEditor,
        els.researchCvEditor,
        els.envEditor,
    ].forEach((editor) => {
        if (!editor) {
            return;
        }
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

const researchFeature = createResearchFeature({
    state,
    els,
    api,
    currentFiles,
    writeDraftToLocalStorage,
    setStatus,
    setResearchRunning,
    updatePreviewCacheBuster: previewFeature.updatePreview,
    updateDiskSnapshot,
    setResearchStatus,
    setResearchOutput,
    setResearchCommandOutput,
    renderResearchState,
    summarizeResearchOutput,
});

const logsFeature = createLogsFeature({
    els,
    api,
    setRunLogOutput,
    summarizeRun,
    setDebugLogOutput,
});

const uiLayoutFeature = createUiLayoutFeature({
    state,
    els,
    localStorageKeys: LS_KEYS,
    onLogsTabActivated: logsFeature.refreshLogs,
    onPreviewUpdate: previewFeature.updatePreview,
    onTailoredTabActivated: refreshTailoredOutput,
    onTabsChanged: updateAutoScrollIndicators,
});

const providerModelFeature = createProviderModelFeature({
    state,
    els,
    localStorageKeys: LS_KEYS,
});

const cvPipelineFeature = createCvPipelineFeature({
    api,
    currentFiles,
    writeDraftToLocalStorage,
    state,
    setRunning,
    startRunStatusTimer,
    stopRunStatusTimer,
    setRunLogOutput,
    setStatus,
    updateDiskSnapshot,
    applyCvOutputState: previewFeature.applyCvOutputState,
    updatePreviewCacheBuster: previewFeature.updatePreview,
    refreshTailoredOutput,
    refreshLogs: logsFeature.refreshLogs,
    summarizeRun,
});

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

async function reloadFromDisk() {
    setRunning(true);
    setStatus("Reloading from disk...");

    try {
        const payload = await api("/api/state");
        applyFilesToEditors(payload.files || {});
        updateDiskSnapshot(payload.files || {});
        previewFeature.applyCvOutputState(payload);
        writeDraftToLocalStorage();
        previewFeature.updatePreview();
        await refreshTailoredOutput();
        setStatus("Reloaded from disk.");
    } catch (err) {
        setStatus(`Reload failed: ${err.message}`, true);
    } finally {
        setRunning(false);
    }
}

async function restartServerFromWeb() {
    const confirmed = window.confirm("Restart the CV web server now?");
    if (!confirmed) {
        return;
    }

    if (els.restartServerBtn) {
        els.restartServerBtn.disabled = true;
    }
    setStatus("Restart requested. Waiting for server...");

    try {
        await api("/api/server/restart", {
            method: "POST",
            body: JSON.stringify({}),
        });
    } catch (_err) {
        // If the server restarts quickly, request may abort. Continue to polling.
    }

    const start = Date.now();
    const maxWaitMs = 20_000;
    while (Date.now() - start < maxWaitMs) {
        try {
            await api("/api/state");
            window.location.reload();
            return;
        } catch (_err) {
            await sleep(600);
        }
    }

    if (els.restartServerBtn) {
        els.restartServerBtn.disabled = false;
    }
    setStatus("Server restart timed out. Refresh the page manually.", true);
}

async function initialize() {
    setStatus("Loading editor state...");
    try {
        const payload = await api("/api/state");
        providerModelFeature.populateProviderAndModelSelect(
            payload.providers || null,
            payload.models || null,
        );
        applyFilesToEditors(payload.files || {});
        updateDiskSnapshot(payload.files || {});
        previewFeature.applyCvOutputState(payload);
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

        const currentResearch = await researchFeature.fetchResearchStatus();
        if (currentResearch.run) {
            setResearchOutput(summarizeResearchOutput(currentResearch.run));
            setResearchCommandOutput(currentResearch.run.command || []);
            if (currentResearch.running) {
                setResearchStatus("Research run in progress...");
                setResearchRunning(true);
                researchFeature
                    .waitForResearchCompletion()
                    .then((run) => {
                        setResearchCommandOutput((run && run.command) || []);
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
            setResearchCommandOutput([]);
        }

        previewFeature.updatePreview();
        await refreshTailoredOutput();

        const savedTab = localStorage.getItem(LS_KEYS.active_tab);
        if (savedTab && els.tabPanels[savedTab]) {
            uiLayoutFeature.setActiveTab(savedTab);
        } else {
            uiLayoutFeature.setActiveTab("cv");
        }

        const savedCvTab = localStorage.getItem(LS_KEYS.active_cv_tab);
        if (savedCvTab && els.cvTabPanels[savedCvTab]) {
            uiLayoutFeature.setActiveCvTab(savedCvTab);
        } else {
            uiLayoutFeature.setActiveCvTab("cv");
        }

        const savedResearchInputTab = localStorage.getItem(LS_KEYS.active_research_input_tab);
        if (savedResearchInputTab && els.researchInputPanels[savedResearchInputTab]) {
            uiLayoutFeature.setActiveResearchInputTab(savedResearchInputTab);
        } else {
            uiLayoutFeature.setActiveResearchInputTab("query");
        }

        const savedLogTab = localStorage.getItem(LS_KEYS.active_log_tab);
        if (savedLogTab && els.logPanels[savedLogTab]) {
            uiLayoutFeature.setActiveLogTab(savedLogTab);
        } else {
            uiLayoutFeature.setActiveLogTab("run");
        }

        const savedResearchOutputTab = localStorage.getItem(LS_KEYS.research_output_tab);
        if (savedResearchOutputTab && els.researchOutputPanels[savedResearchOutputTab]) {
            uiLayoutFeature.setActiveResearchOutputTab(savedResearchOutputTab);
        } else {
            uiLayoutFeature.setActiveResearchOutputTab("console");
        }
    } catch (err) {
        setStatus(`Initialization failed: ${err.message}`, true);
    }
}

els.runFormatBtn.addEventListener("click", () => cvPipelineFeature.runPipeline("format"));
els.runFullBtn.addEventListener("click", () => cvPipelineFeature.runPipeline("full"));
if (els.restartServerBtn) {
    els.restartServerBtn.addEventListener("click", restartServerFromWeb);
}
if (els.runResearchBtn) {
    els.runResearchBtn.addEventListener("click", () => researchFeature.onResearchPrimaryAction());
}
if (els.formatResearchBtn) {
    els.formatResearchBtn.addEventListener("click", () => researchFeature.formatResearchPdf());
}
if (els.resetResearchPromptBtn) {
    els.resetResearchPromptBtn.addEventListener("click", () =>
        researchFeature.resetResearchPrompt(),
    );
}
if (els.copyResearchOutputBtn) {
    els.copyResearchOutputBtn.addEventListener("click", () =>
        researchFeature.copyResearchOutputToClipboard(),
    );
}
els.refreshLogsBtn.addEventListener("click", () => logsFeature.refreshLogs());
els.logSelect.addEventListener("change", () => logsFeature.loadSelectedDebugLog());
els.tabButtons.forEach((button) => {
    button.addEventListener("click", () => uiLayoutFeature.setActiveTab(button.dataset.tab));
});
els.cvTabButtons.forEach((button) => {
    button.addEventListener("click", () => uiLayoutFeature.setActiveCvTab(button.dataset.cvTab));
});
els.researchInputTabButtons.forEach((button) => {
    button.addEventListener("click", () =>
        uiLayoutFeature.setActiveResearchInputTab(button.dataset.researchInputTab),
    );
});
els.logTabButtons.forEach((button) => {
    button.addEventListener("click", () => uiLayoutFeature.setActiveLogTab(button.dataset.logTab));
});
els.researchOutputTabButtons.forEach((button) => {
    button.addEventListener("click", () =>
        uiLayoutFeature.setActiveResearchOutputTab(button.dataset.researchOutputTab),
    );
});
els.fileSaveButtons.forEach((button) => {
    button.addEventListener("click", () => saveSingleFile(button.dataset.file));
});
els.fileLoadButtons.forEach((button) => {
    button.addEventListener("click", () => loadSingleFile(button.dataset.file));
});
if (els.paneSplitter) {
    els.paneSplitter.addEventListener("pointerdown", uiLayoutFeature.onSplitterPointerDown);
    window.addEventListener("pointermove", uiLayoutFeature.onSplitterPointerMove);
    window.addEventListener("pointerup", uiLayoutFeature.onSplitterPointerUp);
    window.addEventListener("pointercancel", uiLayoutFeature.onSplitterPointerUp);
}
els.researchSplitters.forEach((splitter) => {
    splitter.addEventListener("pointerdown", uiLayoutFeature.onResearchSplitterPointerDown);
});
if (els.modelSelect) {
    els.modelSelect.addEventListener("change", () => {
        providerModelFeature.handleModelSelectChanged();
    });
}
if (els.providerSelect) {
    els.providerSelect.addEventListener("change", () => {
        providerModelFeature.handleProviderSelectChanged();
    });
}

bindAutosave();
bindMirroredEditors(els.jobspecEditor, els.researchJobspecEditor);
bindMirroredEditors(els.cvEditor, els.researchCvEditor);
uiLayoutFeature.initializeResearchSectionRatios();
initialize();
