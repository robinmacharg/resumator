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
import { createCvHistoryFeature } from "./js/cv-history-feature.js";
import { createRoleMergeFeature } from "./js/role-merge-feature.js";
import { createRoleRunsFeature } from "./js/role-runs-feature.js";
import { createRoleWorkspaceFeature } from "./js/role-workspace-feature.js";
import { createRunStateFeature } from "./js/run-state-feature.js";
import { createSettingsFeature } from "./js/settings-feature.js";
import { createSteeringFeature } from "./js/steering-feature.js";
import { createThemeFeature } from "./js/theme-feature.js";
import { createUiLayoutFeature } from "./js/ui-layout-feature.js";
import {
    formatCommandForDisplay,
    formatPreviewDateTime,
    formatTimestampToSecond,
    sleep,
} from "./js/app-utils.js";

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
    isDraggingRoleSplitter: false,
    activeResearchSplitter: null,
    researchSectionRatios: [1 / 3, 1 / 3, 1 / 3],
    diskFiles: {},
    runStatusTimerId: null,
    runStatusStartMs: 0,
    runStatusMessage: "",
    // Role mode (multi-role plan): workspace = the DB is in use (false = file mode fallback); activeRoleId null
    // in role mode = no role yet (master CV only).
    workspace: false,
    activeRoleId: null,
    roles: [],
    cvSource: "role",
    cvRuns: [],
    selectedCvRunId: null,
    researchRuns: [],
};

// Phase 2: stable DOM registry collected once and injected into features.
const els = {
    body: document.body,
    statusText: document.getElementById("statusText"),
    activeRoleLabel: document.getElementById("activeRoleLabel"),
    roleTitleBtn: document.getElementById("roleTitleBtn"),
    roleNameInput: document.getElementById("roleNameInput"),
    roleSidebarControls: document.getElementById("roleSidebarControls"),
    roleList: document.getElementById("roleList"),
    newRoleBtn: document.getElementById("newRoleBtn"),
    roleStatusSelect: document.getElementById("roleStatusSelect"),
    deleteRoleBtn: document.getElementById("deleteRoleBtn"),
    newRoleDialog: document.getElementById("newRoleDialog"),
    newRoleForm: document.getElementById("newRoleForm"),
    newRoleNameInput: document.getElementById("newRoleNameInput"),
    newRoleCompanyInput: document.getElementById("newRoleCompanyInput"),
    newRoleJobspecInput: document.getElementById("newRoleJobspecInput"),
    firstRunDialog: document.getElementById("firstRunDialog"),
    firstRunExampleBtn: document.getElementById("firstRunExampleBtn"),
    firstRunBlankBtn: document.getElementById("firstRunBlankBtn"),
    firstRunError: document.getElementById("firstRunError"),
    newRoleCancelBtn: document.getElementById("newRoleCancelBtn"),
    cvSourceSelect: document.getElementById("cvSourceSelect"),
    promoteCvBtn: document.getElementById("promoteCvBtn"),
    pullCvBtn: document.getElementById("pullCvBtn"),
    cvHistoryBtn: document.getElementById("cvHistoryBtn"),
    importCvBtn: document.getElementById("importCvBtn"),
    historyDialog: document.getElementById("historyDialog"),
    historyTitle: document.getElementById("historyTitle"),
    historyList: document.getElementById("historyList"),
    historyContent: document.getElementById("historyContent"),
    historyError: document.getElementById("historyError"),
    historyRestoreBtn: document.getElementById("historyRestoreBtn"),
    historyCloseBtn: document.getElementById("historyCloseBtn"),
    mergeDialog: document.getElementById("mergeDialog"),
    mergeTitle: document.getElementById("mergeTitle"),
    mergeHint: document.getElementById("mergeHint"),
    mergeList: document.getElementById("mergeList"),
    mergeError: document.getElementById("mergeError"),
    mergeApplyBtn: document.getElementById("mergeApplyBtn"),
    mergeCancelBtn: document.getElementById("mergeCancelBtn"),
    runSelect: document.getElementById("runSelect"),
    researchRunSelect: document.getElementById("researchRunSelect"),
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
    settingsDialog: document.getElementById("settingsDialog"),
    settingsOpenBtn: document.getElementById("settingsOpenBtn"),
    settingsCloseBtn: document.getElementById("settingsCloseBtn"),
    settingsTabButtons: Array.from(document.querySelectorAll(".settings-tab-btn")),
    settingsPanels: {
        global: document.getElementById("settingsPanelGlobal"),
        providers: document.getElementById("settingsPanelProviders"),
        other: document.getElementById("settingsPanelOther"),
    },
    settingsStatus: document.getElementById("settingsStatus"),
    settingsImportBtn: document.getElementById("settingsImportBtn"),
    settingsSampleBtn: document.getElementById("settingsSampleBtn"),
    settingsEnvBtn: document.getElementById("settingsEnvBtn"),
    settingsImportPanel: document.getElementById("settingsImportPanel"),
    settingsImportText: document.getElementById("settingsImportText"),
    settingsImportFile: document.getElementById("settingsImportFile"),
    settingsImportMode: document.getElementById("settingsImportMode"),
    settingsImportPreviewBtn: document.getElementById("settingsImportPreviewBtn"),
    settingsImportApplyBtn: document.getElementById("settingsImportApplyBtn"),
    settingsImportCloseBtn: document.getElementById("settingsImportCloseBtn"),
    settingsImportResult: document.getElementById("settingsImportResult"),
    settingsEnvPanel: document.getElementById("settingsEnvPanel"),
    settingsEnvText: document.getElementById("settingsEnvText"),
    settingsEnvRevealBtn: document.getElementById("settingsEnvRevealBtn"),
    settingsEnvCopyBtn: document.getElementById("settingsEnvCopyBtn"),
    settingsEnvDownloadBtn: document.getElementById("settingsEnvDownloadBtn"),
    settingsEnvCloseBtn: document.getElementById("settingsEnvCloseBtn"),
    tailoredViewer: document.getElementById("tailoredViewer"),
    tailoredTitle: document.getElementById("tailoredTitle"),
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
    pdfPreviewDocxLink: document.getElementById("pdfPreviewDocxLink"),
    layout: document.querySelector(".layout"),
    paneSplitter: document.getElementById("paneSplitter"),
    workspace: document.querySelector(".workspace"),
    roleSidebar: document.querySelector(".role-sidebar"),
    roleSplitter: document.getElementById("roleSplitter"),
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
    cvTabButtons: Array.from(document.querySelectorAll(".cv-subtab-btn[data-cv-tab]")),
    researchInputTabButtons: Array.from(document.querySelectorAll(".research-input-tab-btn")),
    cvTabPanels: {
        cv: document.getElementById("tab-cv"),
        prompt: document.getElementById("tab-prompt"),
        jobspec: document.getElementById("tab-jobspec"),
        steering: document.getElementById("tab-steering"),
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
};

// Local storage key registry for persisted UI/editor state.
const LS_KEYS = {
    cv: "cvweb.cv",
    prompt: "cvweb.prompt",
    research_prompt: "cvweb.research_prompt",
    research_company: "cvweb.research.company",
    research_urls: "cvweb.research.urls",
    jobspec: "cvweb.jobspec",
    active_tab: "cvweb.active_tab",
    active_cv_tab: "cvweb.active_cv_tab",
    active_research_input_tab: "cvweb.active_research_input_tab",
    research_section_ratios: "cvweb.research_section_ratios",
    role_sidebar_width: "cvweb.role_sidebar_width",
    active_log_tab: "cvweb.active_log_tab",
    research_output_tab: "cvweb.research_output_tab",
    selected_provider: "cvweb.selected_provider",
    selected_model: "cvweb.selected_model",
    selected_theme: "cvweb.selected_theme",
    steering_text: "cvweb.steering_text",
    steering_enabled: "cvweb.steering_enabled",
    active_role_id: "cvweb.active_role_id",
    // Set once this browser's steering/theme were copied into the first role opened.
    roles_local_copied: "cvweb.roles.local_copied",
};

// Shared preview wiring used across composed features.
const previewBindings = {
    applyCvOutputState: previewFeature.applyCvOutputState,
    applyResearchPreviewState: previewFeature.applyResearchOutputState,
    setCvRunSource: previewFeature.setCvRunSource,
    setResearchRunSource: previewFeature.setResearchRunSource,
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
    setResearchBuiltQueryOutput,
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
    // Late-bound: only called after composition.
    getRoleOwnedKeys: () => roleWorkspaceFeature.getRoleOwnedKeys(),
});

const {
    currentFiles,
    currentFileValues,
    applyRoleFiles,
    syncDirtyIndicators,
    writeDraftToLocalStorage,
    hasLocalDraft,
    loadLocalDraft,
    applyFilesToEditors,
    updateDiskSnapshot,
    bindMirroredEditors,
    bindAutosave,
} = draftFilesFeature;

// Role run history: run picker, preview source and Tailored tab for the active role.
const roleRunsFeature = createRoleRunsFeature({
    state,
    els,
    api,
    setStatus,
    setCvRunSource: previewBindings.setCvRunSource,
    updatePreview: previewBindings.updatePreview,
    formatDateTime: (value) => formatPreviewDateTime(value, "?"),
});

// Role sidebar and role-owned editors (CV, job spec); steering/theme callbacks are late-bound.
const roleWorkspaceFeature = createRoleWorkspaceFeature({
    state,
    els,
    api,
    editableFiles: EDITABLE_FILES,
    localStorageKeys: LS_KEYS,
    setStatus,
    applyRoleFiles,
    syncDirtyIndicators,
    currentFileValues,
    applySteering: (steering) => steeringFeature.applySteering(steering),
    applyTheme: (theme) => themeFeature.applyTheme(theme),
    roleRunsFeature,
    // Late-bound: researchFeature is created further down.
    loadRoleResearch: (roleId) => researchFeature.loadRoleResearch(roleId),
    // settingsFeature is created further down; this only runs after a first-run choice.
    openSettingsStep: () => settingsFeature.openFirstRun(),
});

// Promote to / pull from master: the merge view over the role API, then the open CV is reloaded.
const roleMergeFeature = createRoleMergeFeature({
    state,
    els,
    api,
    setStatus,
    currentFileValues,
    loadOpenCv: roleWorkspaceFeature.loadOpenCv,
});

// Version history of the open CV (role or master): view and restore as a new version.
const cvHistoryFeature = createCvHistoryFeature({
    state,
    els,
    api,
    setStatus,
    currentFileValues,
    loadOpenCv: roleWorkspaceFeature.loadOpenCv,
    formatDateTime: (value) => formatPreviewDateTime(value, "?"),
});

// Role-mode hooks shared by the CV and research run features.
const roleRunDeps = {
    getActiveRoleId: () => state.activeRoleId,
    isRoleRequired: () => roleWorkspaceFeature.isMasterOnly(),
    saveRoleEditsBeforeRun: roleWorkspaceFeature.saveEditsBeforeRun,
};

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
    roleFiles: {
        saveFile: roleWorkspaceFeature.saveFile,
        reloadFile: roleWorkspaceFeature.reloadFile,
        refreshTailoredOutput: roleRunsFeature.refreshTailoredOutput,
    },
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
    setResearchBuiltQueryOutput,
    setResearchCommandOutput,
    renderResearchState,
    summarizeResearchOutput,
    setResearchRunSource: previewBindings.setResearchRunSource,
    formatDateTime: (value) => formatPreviewDateTime(value, "?"),
    ...roleRunDeps,
    afterRoleResearchRun: () => roleWorkspaceFeature.refreshRoles(),
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
// Settings sub-tab: provider keys, models and global options stored in the DB.
const settingsFeature = createSettingsFeature({ els });

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

// Steering note and "Steer CV generation" toggle: on the role in role mode, else in localStorage.
const steeringFeature = createSteeringFeature({
    els,
    localStorageKeys: LS_KEYS,
    onSteeringChanged: roleWorkspaceFeature.handleSteeringChanged,
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
    ...roleRunDeps,
    afterRoleCvRun: async (roleId, run) => {
        await roleRunsFeature.afterCvRun(roleId, run);
        await roleWorkspaceFeature.refreshRoles();
    },
});

// PDF theme selection: on the role in role mode (re-renders the preview), else persisted and re-formatted.
const themeFeature = createThemeFeature({
    state,
    els,
    localStorageKeys: LS_KEYS,
    runPipeline: cvPipelineFeature.runPipeline,
    onThemeChanged: roleWorkspaceFeature.handleThemeChanged,
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
    roleWorkspaceFeature,
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
    roleWorkspaceFeature,
    roleRunsFeature,
    roleMergeFeature,
    cvHistoryFeature,
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

settingsFeature.bind();
appEventBindingsFeature.bindEventHandlers();
appStartupFeature.runStartupSequence();
