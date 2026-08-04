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
    cvPdfExists: false,
    researchPdfExists: false,
    cvPdfMtime: null,
    researchPdfMtime: null,
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
const RESEARCH_SPLITTER_MIN_SECTION_PX = 140;

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

function normalizeResearchRatios(ratios) {
    if (!Array.isArray(ratios) || ratios.length !== 3) {
        return [1 / 3, 1 / 3, 1 / 3];
    }

    const cleaned = ratios.map((value) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
    });
    const sum = cleaned.reduce((acc, value) => acc + value, 0);

    if (sum <= 0) {
        return [1 / 3, 1 / 3, 1 / 3];
    }

    return cleaned.map((value) => value / sum);
}

function applyResearchSectionRatios(ratios, persist = true) {
    const panel = els.tabPanels.research;
    if (!panel) {
        return;
    }

    const normalized = normalizeResearchRatios(ratios);
    state.researchSectionRatios = normalized;

    panel.style.setProperty("--research-top-size", `${(normalized[0] * 100).toFixed(4)}%`);
    panel.style.setProperty("--research-middle-size", `${(normalized[1] * 100).toFixed(4)}%`);
    panel.style.setProperty("--research-bottom-size", `${(normalized[2] * 100).toFixed(4)}%`);

    if (persist) {
        localStorage.setItem(LS_KEYS.research_section_ratios, JSON.stringify(normalized));
    }
}

function initializeResearchSectionRatios() {
    const savedRaw = localStorage.getItem(LS_KEYS.research_section_ratios);
    if (!savedRaw) {
        applyResearchSectionRatios([1 / 3, 1 / 3, 1 / 3], false);
        return;
    }

    try {
        const parsed = JSON.parse(savedRaw);
        applyResearchSectionRatios(parsed, false);
    } catch (_err) {
        applyResearchSectionRatios([1 / 3, 1 / 3, 1 / 3], false);
    }
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

function selectedModelFromUi() {
    if (!els.modelSelect) {
        return "";
    }
    return (els.modelSelect.value || "").trim();
}

function selectedProviderFromUi() {
    if (!els.providerSelect) {
        return state.defaultProvider || "gemini";
    }
    return (els.providerSelect.value || state.defaultProvider || "gemini").trim();
}

function setSelectedProvider(provider) {
    const next = (provider || state.defaultProvider || "gemini").trim();
    state.selectedProvider = next;
    localStorage.setItem(LS_KEYS.selected_provider, next);
    if (els.providerSelect && els.providerSelect.value !== next) {
        els.providerSelect.value = next;
    }
}

function setSelectedModel(model) {
    const next = (model || "").trim();
    state.selectedModel = next;
    localStorage.setItem(LS_KEYS.selected_model, next);
    if (els.modelSelect && els.modelSelect.value !== next) {
        els.modelSelect.value = next;
    }
}

function getActiveModelOptions() {
    const options = state.modelsByProvider[state.selectedProvider];
    return Array.isArray(options) ? options : [];
}

function refreshModelSelectOptions() {
    if (!els.modelSelect) {
        return;
    }

    const defaultOptionValue = "";
    const defaultOptionLabel = "Default order";
    const modelOptions = getActiveModelOptions();

    const deduped = [];
    const seen = new Set();
    modelOptions.forEach((item) => {
        const cleaned = item.trim();
        if (!cleaned || seen.has(cleaned)) {
            return;
        }
        seen.add(cleaned);
        deduped.push(cleaned);
    });

    els.modelSelect.innerHTML = "";

    const defaultOpt = document.createElement("option");
    defaultOpt.value = defaultOptionValue;
    defaultOpt.textContent = defaultOptionLabel;
    els.modelSelect.appendChild(defaultOpt);

    deduped.forEach((modelName) => {
        const opt = document.createElement("option");
        opt.value = modelName;
        opt.textContent = modelName;
        els.modelSelect.appendChild(opt);
    });

    const savedSelection = (localStorage.getItem(LS_KEYS.selected_model) || "").trim();
    const currentSelection = (state.selectedModel || "").trim();
    const selectedCandidate = currentSelection || savedSelection;
    const selected = deduped.includes(selectedCandidate) ? selectedCandidate : defaultOptionValue;
    setSelectedModel(selected);
}

function populateProviderAndModelSelect(providersPayload, modelsPayload) {
    const defaultProvider =
        providersPayload && typeof providersPayload.defaultProvider === "string"
            ? providersPayload.defaultProvider.trim() || "gemini"
            : "gemini";
    state.defaultProvider = defaultProvider;

    const providerOptions =
        providersPayload && Array.isArray(providersPayload.options)
            ? providersPayload.options
                  .filter(
                      (item) =>
                          item && typeof item.value === "string" && typeof item.label === "string",
                  )
                  .map((item) => ({
                      value: item.value.trim(),
                      label: item.label.trim(),
                      enabled: item.enabled !== false,
                      disabledReason:
                          typeof item.disabledReason === "string" ? item.disabledReason.trim() : "",
                  }))
                  .filter((item) => item.value && item.label)
            : [{ value: "gemini", label: "Gemini", enabled: true, disabledReason: "" }];

    if (els.providerSelect) {
        els.providerSelect.innerHTML = "";
        providerOptions.forEach((item) => {
            const opt = document.createElement("option");
            opt.value = item.value;
            opt.textContent = item.enabled ? item.label : `${item.label} (disabled)`;
            opt.disabled = !item.enabled;
            if (!item.enabled && item.disabledReason) {
                opt.title = item.disabledReason;
            }
            els.providerSelect.appendChild(opt);
        });
    }

    state.modelsByProvider =
        modelsPayload && modelsPayload.byProvider && typeof modelsPayload.byProvider === "object"
            ? Object.fromEntries(
                  Object.entries(modelsPayload.byProvider).map(([provider, models]) => {
                      const cleaned = Array.isArray(models)
                          ? models
                                .filter((item) => typeof item === "string" && item.trim())
                                .map((item) => item.trim())
                          : [];
                      return [provider, cleaned];
                  }),
              )
            : {};

    const savedProvider = (localStorage.getItem(LS_KEYS.selected_provider) || "").trim();
    const enabledProviders = providerOptions
        .filter((item) => item.enabled)
        .map((item) => item.value);
    const fallbackProviders = providerOptions.map((item) => item.value);
    const selectedProvider = enabledProviders.includes(savedProvider)
        ? savedProvider
        : enabledProviders.includes(defaultProvider)
          ? defaultProvider
          : enabledProviders[0] || fallbackProviders[0] || "gemini";
    setSelectedProvider(selectedProvider);
    refreshModelSelectOptions();
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
    const isResearchTab = state.activeTab === "research";
    const isResearchDoc = isResearchTab;
    const targetName = isResearchDoc ? "research_output.formatted.pdf" : "tailored_dev.pdf";
    const exists = isResearchDoc ? state.researchPdfExists : state.cvPdfExists;
    const targetLabel = isResearchDoc ? "Research" : "CV";
    const targetMtime = isResearchDoc ? state.researchPdfMtime : state.cvPdfMtime;

    if (els.pdfPreviewTitle) {
        const generatedText = formatMtimeForPreview(targetMtime);
        els.pdfPreviewTitle.textContent = `PDF Preview (${targetLabel}, Generated: ${generatedText})`;
    }

    if (els.pdfPreviewOpenLink) {
        els.pdfPreviewOpenLink.href = `/output/${targetName}`;
        els.pdfPreviewOpenLink.style.pointerEvents = exists ? "auto" : "none";
        els.pdfPreviewOpenLink.style.opacity = exists ? "1" : "0.45";
    }

    if (exists) {
        const ts = Date.now();
        els.pdfPreview.classList.remove("hidden");
        if (els.pdfPlaceholder) {
            els.pdfPlaceholder.classList.remove("visible");
        }
        els.pdfPreview.src = `/output/${targetName}?ts=${ts}`;
    } else {
        els.pdfPreview.classList.add("hidden");
        if (els.pdfPlaceholder) {
            els.pdfPlaceholder.classList.add("visible");
            els.pdfPlaceholder.textContent = "No document availabel";
        }
    }
}

function formatMtimeForPreview(mtimeSeconds) {
    if (typeof mtimeSeconds !== "number" || !Number.isFinite(mtimeSeconds) || mtimeSeconds <= 0) {
        return "-";
    }

    const date = new Date(mtimeSeconds * 1000);
    if (Number.isNaN(date.getTime())) {
        return "-";
    }

    const pad2 = (n) => String(n).padStart(2, "0");
    const day = pad2(date.getDate());
    const month = pad2(date.getMonth() + 1);
    const year = date.getFullYear();
    const hours = pad2(date.getHours());
    const mins = pad2(date.getMinutes());
    const secs = pad2(date.getSeconds());
    return `${day}/${month}/${year} - ${hours}:${mins}:${secs}`;
}

function applyCvOutputState(payload) {
    const outputs = (payload && payload.outputs) || {};
    state.cvPdfExists = Boolean(outputs.pdfExists);
    state.cvPdfMtime =
        typeof outputs.pdfMtime === "number" && Number.isFinite(outputs.pdfMtime)
            ? outputs.pdfMtime
            : null;
}

function applyResearchOutputState(payload) {
    const output = (payload && payload.output) || {};
    state.researchPdfExists = Boolean(output.formattedPdfExists);
    state.researchPdfMtime =
        typeof output.formattedPdfMtime === "number" && Number.isFinite(output.formattedPdfMtime)
            ? output.formattedPdfMtime
            : null;
}

function setRunLogOutput(text) {
    setOutputContentWithSmartAutoscroll(els.runLogOutput, text);
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

function shellQuote(arg) {
    if (arg === "") {
        return "''";
    }
    if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(arg)) {
        return arg;
    }
    return `'${String(arg).replace(/'/g, `'\\''`)}'`;
}

function formatCommandForDisplay(command) {
    if (!Array.isArray(command) || command.length === 0) {
        return "No command yet. Run Research first.";
    }
    return command.map((part) => shellQuote(String(part))).join(" ");
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

function formatTimestampToSecond(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) {
        return new Date().toLocaleString();
    }
    const pad2 = (n) => String(n).padStart(2, "0");
    const year = date.getFullYear();
    const month = pad2(date.getMonth() + 1);
    const day = pad2(date.getDate());
    const hours = pad2(date.getHours());
    const mins = pad2(date.getMinutes());
    const secs = pad2(date.getSeconds());
    return `${year}-${month}-${day} ${hours}:${mins}:${secs}`;
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

    applyResearchOutputState(payload);

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
            setResearchCommandOutput(run.command || []);
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
                autoFormatPdf: true,
                selectedProvider: state.selectedProvider || "gemini",
                selectedModel: state.selectedModel || "",
            }),
        });

        if (kickoff.run) {
            setResearchOutput(summarizeResearchOutput(kickoff.run));
            setResearchCommandOutput(kickoff.run.command || []);
        }

        const run = await waitForResearchCompletion();
        if (run && run.stoppedByUser) {
            setResearchStatus(`Research stopped (${run.elapsedSeconds}s).`);
            setStatus("Research run stopped.");
        } else if (run && run.success) {
            setResearchStatus(`Research complete (${run.elapsedSeconds}s).`);
            setStatus("Research run complete.");
        } else {
            setResearchStatus("Research run failed.", true);
            setStatus("Research run failed. See Research Output.", true);
        }

        const refreshed = await api("/api/research/state");
        renderResearchState(refreshed);
        updatePreviewCacheBuster();
    } catch (err) {
        setResearchStatus(`Research run failed: ${err.message}`, true);
        setResearchOutput(err.stack || err.message);
        setStatus(`Research run failed: ${err.message}`, true);
    } finally {
        setResearchRunning(false);
    }
}

async function stopResearch() {
    setResearchStatus("Stopping research run...");
    setStatus("Stopping research run...");

    try {
        await api("/api/research/stop", {
            method: "POST",
            body: JSON.stringify({}),
        });
        setResearchStatus("Stop requested. Waiting for process to exit...");
    } catch (err) {
        setResearchStatus(`Failed to stop research run: ${err.message}`, true);
        setStatus(`Failed to stop research run: ${err.message}`, true);
    }
}

function onResearchPrimaryAction() {
    if (state.isResearchRunning) {
        const shouldStop = window.confirm("Stop the current research run?");
        if (!shouldStop) {
            return;
        }
        stopResearch();
        return;
    }
    runResearch();
}

async function formatResearchPdf() {
    setResearchRunning(true);
    setResearchStatus("Formatting research PDF...");

    try {
        const kickoff = await api("/api/research/format", {
            method: "POST",
            body: JSON.stringify({}),
        });

        if (kickoff.run) {
            setResearchOutput(summarizeResearchOutput(kickoff.run));
            setResearchCommandOutput(kickoff.run.command || []);
        }

        const run = await waitForResearchCompletion();
        if (run && run.success) {
            setResearchStatus(`Research PDF formatted (${run.elapsedSeconds}s).`);
            setStatus("Research PDF formatting complete.");
        } else {
            setResearchStatus("Research PDF formatting failed.", true);
            setStatus("Research PDF formatting failed. See Research Output.", true);
        }

        const refreshed = await api("/api/research/state");
        renderResearchState(refreshed);
        updatePreviewCacheBuster();
    } catch (err) {
        setResearchStatus(`Research PDF formatting failed: ${err.message}`, true);
        setStatus(`Research PDF formatting failed: ${err.message}`, true);
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
    const sourceText =
        state.activeResearchOutputTab === "command"
            ? els.researchCommandOutput && els.researchCommandOutput.value
                ? els.researchCommandOutput.value
                : ""
            : state.activeResearchOutputTab === "built_query"
              ? els.researchBuiltQueryOutput && els.researchBuiltQueryOutput.textContent
                  ? els.researchBuiltQueryOutput.textContent
                  : ""
              : els.researchOutput && els.researchOutput.textContent
                ? els.researchOutput.textContent
                : "";

    const text = sourceText.trim();
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
        setOutputContentWithSmartAutoscroll(
            els.debugLogOutput,
            payload.content || "(Empty log file)",
        );
    } catch (err) {
        setOutputContentWithSmartAutoscroll(
            els.debugLogOutput,
            `Unable to load log file: ${err.message}`,
        );
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
            body: JSON.stringify({
                files: currentFiles(),
                selectedProvider: state.selectedProvider || "gemini",
                selectedModel: state.selectedModel || "",
            }),
        });
        if (kickoff.run) {
            setRunLogOutput(summarizeRun(kickoff.run));
        }

        const run = await waitForRunCompletion();

        const refreshedState = await api("/api/state");
        if (refreshedState.files) {
            updateDiskSnapshot(refreshedState.files);
        }
        applyCvOutputState(refreshedState);

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
        applyCvOutputState(payload);
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

function setActiveTab(tabName) {
    if (!els.tabPanels[tabName]) {
        return;
    }

    state.activeTab = tabName;
    localStorage.setItem(LS_KEYS.active_tab, tabName);
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
    }

    updatePreviewCacheBuster();
}

function setActiveCvTab(tabName) {
    if (!els.cvTabPanels[tabName]) {
        return;
    }

    state.activeCvTab = tabName;
    localStorage.setItem(LS_KEYS.active_cv_tab, tabName);

    els.cvTabButtons.forEach((button) => {
        const isActive = button.dataset.cvTab === tabName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    Object.entries(els.cvTabPanels).forEach(([name, panel]) => {
        panel.classList.toggle("active", name === tabName);
    });

    if (tabName === "tailored") {
        refreshTailoredOutput();
    }
}

function setActiveResearchInputTab(tabName) {
    if (!els.researchInputPanels[tabName]) {
        return;
    }

    state.activeResearchInputTab = tabName;
    localStorage.setItem(LS_KEYS.active_research_input_tab, tabName);

    els.researchInputTabButtons.forEach((button) => {
        const isActive = button.dataset.researchInputTab === tabName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    Object.entries(els.researchInputPanels).forEach(([name, panel]) => {
        panel.classList.toggle("active", name === tabName);
    });
}

function setActiveLogTab(tabName) {
    if (!els.logPanels[tabName]) {
        return;
    }

    state.activeLogTab = tabName;
    localStorage.setItem(LS_KEYS.active_log_tab, tabName);
    els.logTabButtons.forEach((button) => {
        const isActive = button.dataset.logTab === tabName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    Object.entries(els.logPanels).forEach(([name, panel]) => {
        panel.classList.toggle("active", name === tabName);
    });

    updateAutoScrollIndicators();
}

function setActiveResearchOutputTab(tabName) {
    if (!els.researchOutputPanels[tabName]) {
        return;
    }

    state.activeResearchOutputTab = tabName;
    localStorage.setItem(LS_KEYS.research_output_tab, tabName);

    els.researchOutputTabButtons.forEach((button) => {
        const isActive = button.dataset.researchOutputTab === tabName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    Object.entries(els.researchOutputPanels).forEach(([name, panel]) => {
        panel.classList.toggle("active", name === tabName);
    });

    updateAutoScrollIndicators();
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

function onResearchSplitterPointerDown(event) {
    if (!els.tabPanels.research || window.matchMedia("(max-width: 1100px)").matches) {
        return;
    }

    const splitter = event.currentTarget;
    if (!splitter || !splitter.dataset || !splitter.dataset.researchSplitter) {
        return;
    }

    const panelRect = els.tabPanels.research.getBoundingClientRect();
    const splitterCount = 2;
    const splitterSize = 6;
    const availableHeight = Math.max(panelRect.height - splitterCount * splitterSize, 1);
    const currentHeights = state.researchSectionRatios.map((ratio) => ratio * availableHeight);

    state.isDraggingResearchSplitter = true;
    state.activeResearchSplitter = {
        key: splitter.dataset.researchSplitter,
        startY: event.clientY,
        startHeights: currentHeights,
        element: splitter,
    };

    splitter.classList.add("dragging");
    splitter.setPointerCapture(event.pointerId);
}

function onSplitterPointerMove(event) {
    if (!state.isDraggingSplitter) {
        if (!state.isDraggingResearchSplitter || !state.activeResearchSplitter) {
            return;
        }

        const drag = state.activeResearchSplitter;
        const nextHeights = [...drag.startHeights];
        const deltaY = event.clientY - drag.startY;
        const minSection = RESEARCH_SPLITTER_MIN_SECTION_PX;

        if (drag.key === "top") {
            nextHeights[0] += deltaY;
            nextHeights[1] -= deltaY;

            if (nextHeights[0] < minSection) {
                nextHeights[1] -= minSection - nextHeights[0];
                nextHeights[0] = minSection;
            }
            if (nextHeights[1] < minSection) {
                nextHeights[0] -= minSection - nextHeights[1];
                nextHeights[1] = minSection;
            }
        } else {
            nextHeights[1] += deltaY;
            nextHeights[2] -= deltaY;

            if (nextHeights[1] < minSection) {
                nextHeights[2] -= minSection - nextHeights[1];
                nextHeights[1] = minSection;
            }
            if (nextHeights[2] < minSection) {
                nextHeights[1] -= minSection - nextHeights[2];
                nextHeights[2] = minSection;
            }
        }

        const total = nextHeights.reduce((acc, value) => acc + value, 0);
        if (total > 0) {
            applyResearchSectionRatios(nextHeights.map((value) => value / total));
        }
        return;
    }
    updateSplitterPosition(event.clientX);
}

function onSplitterPointerUp(event) {
    if (state.isDraggingResearchSplitter && state.activeResearchSplitter) {
        const drag = state.activeResearchSplitter;
        state.isDraggingResearchSplitter = false;
        state.activeResearchSplitter = null;
        if (drag.element) {
            drag.element.classList.remove("dragging");
            try {
                drag.element.releasePointerCapture(event.pointerId);
            } catch (_err) {
                // Ignore capture release errors when pointer is no longer active.
            }
        }
    }

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
        populateProviderAndModelSelect(payload.providers || null, payload.models || null);
        applyFilesToEditors(payload.files || {});
        updateDiskSnapshot(payload.files || {});
        applyCvOutputState(payload);
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
            setResearchCommandOutput(currentResearch.run.command || []);
            if (currentResearch.running) {
                setResearchStatus("Research run in progress...");
                setResearchRunning(true);
                waitForResearchCompletion()
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

        updatePreviewCacheBuster();
        await refreshTailoredOutput();

        const savedTab = localStorage.getItem(LS_KEYS.active_tab);
        if (savedTab && els.tabPanels[savedTab]) {
            setActiveTab(savedTab);
        } else {
            setActiveTab("cv");
        }

        const savedCvTab = localStorage.getItem(LS_KEYS.active_cv_tab);
        if (savedCvTab && els.cvTabPanels[savedCvTab]) {
            setActiveCvTab(savedCvTab);
        } else {
            setActiveCvTab("cv");
        }

        const savedResearchInputTab = localStorage.getItem(LS_KEYS.active_research_input_tab);
        if (savedResearchInputTab && els.researchInputPanels[savedResearchInputTab]) {
            setActiveResearchInputTab(savedResearchInputTab);
        } else {
            setActiveResearchInputTab("query");
        }

        const savedLogTab = localStorage.getItem(LS_KEYS.active_log_tab);
        if (savedLogTab && els.logPanels[savedLogTab]) {
            setActiveLogTab(savedLogTab);
        } else {
            setActiveLogTab("run");
        }

        const savedResearchOutputTab = localStorage.getItem(LS_KEYS.research_output_tab);
        if (savedResearchOutputTab && els.researchOutputPanels[savedResearchOutputTab]) {
            setActiveResearchOutputTab(savedResearchOutputTab);
        } else {
            setActiveResearchOutputTab("console");
        }
    } catch (err) {
        setStatus(`Initialization failed: ${err.message}`, true);
    }
}

els.runFormatBtn.addEventListener("click", () => runPipeline("format"));
els.runFullBtn.addEventListener("click", () => runPipeline("full"));
if (els.restartServerBtn) {
    els.restartServerBtn.addEventListener("click", restartServerFromWeb);
}
if (els.runResearchBtn) {
    els.runResearchBtn.addEventListener("click", onResearchPrimaryAction);
}
if (els.formatResearchBtn) {
    els.formatResearchBtn.addEventListener("click", formatResearchPdf);
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
els.cvTabButtons.forEach((button) => {
    button.addEventListener("click", () => setActiveCvTab(button.dataset.cvTab));
});
els.researchInputTabButtons.forEach((button) => {
    button.addEventListener("click", () =>
        setActiveResearchInputTab(button.dataset.researchInputTab),
    );
});
els.logTabButtons.forEach((button) => {
    button.addEventListener("click", () => setActiveLogTab(button.dataset.logTab));
});
els.researchOutputTabButtons.forEach((button) => {
    button.addEventListener("click", () =>
        setActiveResearchOutputTab(button.dataset.researchOutputTab),
    );
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
els.researchSplitters.forEach((splitter) => {
    splitter.addEventListener("pointerdown", onResearchSplitterPointerDown);
});
if (els.modelSelect) {
    els.modelSelect.addEventListener("change", () => {
        setSelectedModel(selectedModelFromUi());
    });
}
if (els.providerSelect) {
    els.providerSelect.addEventListener("change", () => {
        setSelectedProvider(selectedProviderFromUi());
        setSelectedModel("");
        refreshModelSelectOptions();
    });
}

bindAutosave();
bindMirroredEditors(els.jobspecEditor, els.researchJobspecEditor);
bindMirroredEditors(els.cvEditor, els.researchCvEditor);
initializeResearchSectionRatios();
initialize();
