/**
 * Architecture role:
 * - Layer: frontend composition root for the CV web app.
 * - Responsibility: create shared state, collect DOM references, compose feature modules, and wire events.
 *
 * Plain-language purpose:
 * - This is the app's "main" file. It does not implement every behavior itself; instead it connects smaller features together.
 */

import { api, fetchText } from "./js/api-client.js";
import { createAppEventBindingsFeature } from "./js/app-event-bindings-feature.js";
import { createAppInitializationFeature } from "./js/app-initialization-feature.js";
import { createAppOperationsFeature } from "./js/app-operations-feature.js";
import { createAppStartupFeature } from "./js/app-startup-feature.js";
import { createCvPipelineFeature } from "./js/cv-pipeline-feature.js";
import { createDraftFilesFeature } from "./js/draft-files-feature.js";
import { createLogsFeature } from "./js/logs-feature.js";
import { createOutputDisplayFeature } from "./js/output-display-feature.js";
import { createPdfPreviewFeature } from "./js/pdf-preview-feature.js";
import { createProviderModelFeature } from "./js/provider-model-feature.js";
import { createResearchFeature } from "./js/research-feature.js";
import { createRunStateFeature } from "./js/run-state-feature.js";
import { createSteeringFeature } from "./js/steering-feature.js";
import { createThemeFeature } from "./js/theme-feature.js";
import { createUiLayoutFeature } from "./js/ui-layout-feature.js";
import { formatCommandForDisplay, formatTimestampToSecond, sleep } from "./js/app-utils.js";

// Phase 1: shared runtime state used across feature modules.
const state = {
    isRunning: false,
    isResearchRunning: false,
    selectedProvider: "gemini",
    selectedModel: "",
    selectedTheme: "default",
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

// Phase 2: stable DOM registry collected once and injected into features.
const els = {
    statusText: document.getElementById("statusText"),
    providerSelect: document.getElementById("providerSelect"),
    modelSelect: document.getElementById("modelSelect"),
    themeSelect: document.getElementById("themeSelect"),
    steeringEditor: document.getElementById("steeringEditor"),
    steerCheckbox: document.getElementById("steerCheckbox"),
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
        steering: document.getElementById("tab-steering"),
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
    // Editable file metadata used by draft/save/load flows and tab dirty indicators.
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

// Local storage key registry for persisted UI/editor state.
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
    selected_theme: "cvweb.selected_theme",
    steering_text: "cvweb.steering_text",
    steering_enabled: "cvweb.steering_enabled",
};

// Shared preview wiring used across composed features.
const previewBindings = {
    applyCvOutputState: previewFeature.applyCvOutputState,
    applyResearchPreviewState: previewFeature.applyResearchOutputState,
    updatePreview: previewFeature.updatePreview,
};

// Phase 3: compose foundational display and state-control features.
// Shared PDF preview presenter for CV and Research outputs.
const outputDisplayFeature = createOutputDisplayFeature({
    state,
    els,
    formatCommandForDisplay,
    formatTimestampToSecond,
    applyResearchPreviewState: previewBindings.applyResearchPreviewState,
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

// Shared run-state controller (busy flags, timer, control disabling, button state).
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

// Phase 4: compose content/draft and operation workflow features.
// Draft and editor synchronization feature for local state persistence.
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

// Shared dependency bundles reused by workflow features.
const workflowDeps = {
    api,
    currentFiles,
    writeDraftToLocalStorage,
    setStatus,
    updateDiskSnapshot,
};

const previewWorkflowDeps = {
    applyCvOutputState: previewBindings.applyCvOutputState,
    updatePreviewCacheBuster: previewBindings.updatePreview,
};

// File operation and server lifecycle actions (save/load/reload/restart).
const appOperationsFeature = createAppOperationsFeature({
    els,
    editableFiles: EDITABLE_FILES,
    ...workflowDeps,
    fetchText,
    sleep,
    applyFilesToEditors,
    applyCvOutputState: previewBindings.applyCvOutputState,
    updatePreview: previewBindings.updatePreview,
    setRunning,
});

const { refreshTailoredOutput } = appOperationsFeature;

// Research workflow orchestration (run/stop/format/reset/copy).
const researchFeature = createResearchFeature({
    state,
    els,
    ...workflowDeps,
    setResearchRunning,
    updatePreviewCacheBuster: previewWorkflowDeps.updatePreviewCacheBuster,
    setResearchStatus,
    setResearchOutput,
    setResearchCommandOutput,
    renderResearchState,
    summarizeResearchOutput,
});

// Logs retrieval and selection handling.
const logsFeature = createLogsFeature({
    els,
    api,
    setRunLogOutput,
    summarizeRun,
    setDebugLogOutput,
});

// Phase 5: compose layout/config/workflow orchestration features.
// Layout and tab interaction manager.
const uiLayoutFeature = createUiLayoutFeature({
    state,
    els,
    localStorageKeys: LS_KEYS,
    onLogsTabActivated: logsFeature.refreshLogs,
    onPreviewUpdate: previewBindings.updatePreview,
    onTailoredTabActivated: refreshTailoredOutput,
    onTabsChanged: updateAutoScrollIndicators,
});

// Provider/model selection and persistence manager.
const providerModelFeature = createProviderModelFeature({
    state,
    els,
    localStorageKeys: LS_KEYS,
});

// Steering note and "Steer CV generation" toggle, kept in localStorage.
const steeringFeature = createSteeringFeature({
    els,
    localStorageKeys: LS_KEYS,
});

// CV pipeline run orchestrator and polling coordinator.
const cvPipelineFeature = createCvPipelineFeature({
    ...workflowDeps,
    state,
    getSteeringRequest: steeringFeature.getSteeringRequest,
    setRunning,
    startRunStatusTimer,
    stopRunStatusTimer,
    setRunLogOutput,
    ...previewWorkflowDeps,
    refreshTailoredOutput,
    refreshLogs: logsFeature.refreshLogs,
    summarizeRun,
});

// PDF theme selection: persisted, and re-runs formatting on change.
const themeFeature = createThemeFeature({
    state,
    els,
    localStorageKeys: LS_KEYS,
    runPipeline: cvPipelineFeature.runPipeline,
});

// Startup state restoration coordinator.
const appInitializationFeature = createAppInitializationFeature({
    ...workflowDeps,
    els,
    localStorageKeys: LS_KEYS,
    providerModelFeature,
    themeFeature,
    steeringFeature,
    uiLayoutFeature,
    researchFeature,
    applyFilesToEditors,
    applyCvOutputState: previewBindings.applyCvOutputState,
    renderResearchState,
    hasLocalDraft,
    loadLocalDraft,
    syncDirtyIndicators,
    setRunLogOutput,
    summarizeRun,
    summarizeResearchOutput,
    setResearchOutput,
    setResearchCommandOutput,
    setResearchStatus,
    setResearchRunning,
    updatePreview: previewBindings.updatePreview,
    refreshTailoredOutput,
});

const { initialize } = appInitializationFeature;

// Phase 6: bind UI events, then run startup sequence.
// UI event attachment map.
const appEventBindingsFeature = createAppEventBindingsFeature({
    els,
    cvPipelineFeature,
    appOperationsFeature,
    researchFeature,
    logsFeature,
    uiLayoutFeature,
    providerModelFeature,
    themeFeature,
    steeringFeature,
});

// Final startup launcher for one-time app boot order.
const appStartupFeature = createAppStartupFeature({
    els,
    bindAutosave,
    bindMirroredEditors,
    uiLayoutFeature,
    syncResearchPrimaryButton,
    initialize,
});

appEventBindingsFeature.bindEventHandlers();
appStartupFeature.runStartupSequence();
