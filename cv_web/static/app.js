/**
 * Architecture role:
 * - Layer: frontend composition root for the CV web app.
 * - Responsibility: create shared state, collect DOM references, compose feature modules, and wire events.
 *
 * Plain-language purpose:
 * - This is the app's "main" file. It does not implement every behavior itself; instead it connects smaller features together.
 */

import { api, fetchText } from "./js/api-client.js";
import { createAppOperationsFeature } from "./js/app-operations-feature.js";
import { createCvPipelineFeature } from "./js/cv-pipeline-feature.js";
import { createDraftFilesFeature } from "./js/draft-files-feature.js";
import { createLogsFeature } from "./js/logs-feature.js";
import { createOutputDisplayFeature } from "./js/output-display-feature.js";
import { createPdfPreviewFeature } from "./js/pdf-preview-feature.js";
import { createProviderModelFeature } from "./js/provider-model-feature.js";
import { createResearchFeature } from "./js/research-feature.js";
import { createRunStateFeature } from "./js/run-state-feature.js";
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

const outputDisplayFeature = createOutputDisplayFeature({
    state,
    els,
    formatCommandForDisplay,
    formatTimestampToSecond,
    applyResearchPreviewState: previewFeature.applyResearchOutputState,
});

const {
    setStatus,
    updateAutoScrollIndicators,
    setRunLogOutput,
    setDebugLogOutput,
    setResearchStatus,
    setResearchOutput,
    setResearchCommandOutput,
    summarizeRun,
    summarizeResearchOutput,
    renderResearchState,
} = outputDisplayFeature;

const runStateFeature = createRunStateFeature({
    state,
    els,
    setStatus,
});

const {
    startRunStatusTimer,
    stopRunStatusTimer,
    setRunning,
    setResearchRunning,
    syncResearchPrimaryButton,
} = runStateFeature;

const draftFilesFeature = createDraftFilesFeature({
    state,
    els,
    editableFiles: EDITABLE_FILES,
    localStorageKeys: LS_KEYS,
    setStatus,
});

const {
    currentFiles,
    syncDirtyIndicators,
    writeDraftToLocalStorage,
    hasLocalDraft,
    loadLocalDraft,
    applyFilesToEditors,
    updateDiskSnapshot,
    bindMirroredEditors,
    bindAutosave,
} = draftFilesFeature;

const appOperationsFeature = createAppOperationsFeature({
    els,
    editableFiles: EDITABLE_FILES,
    api,
    fetchText,
    sleep,
    currentFiles,
    writeDraftToLocalStorage,
    updateDiskSnapshot,
    applyFilesToEditors,
    applyCvOutputState: previewFeature.applyCvOutputState,
    updatePreview: previewFeature.updatePreview,
    setRunning,
    setStatus,
});

const {
    refreshTailoredOutput,
    saveSingleFile,
    loadSingleFile,
    saveToDisk,
    reloadFromDisk,
    restartServerFromWeb,
} = appOperationsFeature;

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

/**
 * Initialize app state, tabs, providers/models, logs, and research state.
 * @returns {Promise<void>}
 */
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
