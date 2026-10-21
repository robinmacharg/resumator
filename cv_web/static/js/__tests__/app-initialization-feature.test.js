import test from "node:test";
import assert from "node:assert/strict";

import { createAppInitializationFeature } from "../app-initialization-feature.js";

function createLocalStorageMock() {
    const store = new Map();
    return {
        getItem(key) {
            return store.has(key) ? store.get(key) : null;
        },
        setItem(key, value) {
            store.set(key, String(value));
        },
    };
}

function createHarness(options = {}) {
    global.localStorage = createLocalStorageMock();

    const calls = {
        api: [],
        setStatus: [],
        providerPopulate: [],
        applyFilesToEditors: [],
        updateDiskSnapshot: [],
        applyCvOutputState: [],
        renderResearchState: [],
        loadLocalDraft: [],
        writeDraftToLocalStorage: 0,
        syncDirtyIndicators: 0,
        setRunLogOutput: [],
        setResearchOutput: [],
        setResearchCommandOutput: [],
        setResearchStatus: [],
        setResearchRunning: [],
        updatePreview: 0,
        refreshTailoredOutput: 0,
        uiLayout: {
            activeTab: [],
            activeCvTab: [],
            activeResearchInputTab: [],
            activeLogTab: [],
            activeResearchOutputTab: [],
        },
    };

    const localStorageKeys = {
        active_tab: "active_tab",
        active_cv_tab: "active_cv_tab",
        active_research_input_tab: "active_research_input_tab",
        active_log_tab: "active_log_tab",
        research_output_tab: "research_output_tab",
    };

    const els = {
        tabPanels: { cv: {}, logs: {}, research: {} },
        cvTabPanels: { cv: {}, tailored: {} },
        researchInputPanels: { query: {}, prompt: {} },
        logPanels: { run: {}, debug: {} },
        researchOutputPanels: { console: {}, command: {} },
    };

    const statePayload = options.statePayload || {
        files: { cv: "cv", prompt: "prompt", research_prompt: "rp", jobspec: "job", env: "env" },
        providers: {
            defaultProvider: "gemini",
            options: [{ value: "gemini", label: "Gemini", enabled: true }],
        },
        models: { byProvider: { gemini: ["gemini-2.5-pro"] } },
        lastRun: { id: "run1" },
    };

    const researchStatePayload = options.researchStatePayload || { reportPath: "research.md" };
    const researchStatusPayload =
        options.researchStatusPayload === undefined
            ? { run: null, running: false }
            : options.researchStatusPayload;

    const api = async (path) => {
        calls.api.push(path);
        if (options.apiError && path === options.apiError.path) {
            throw new Error(options.apiError.message);
        }
        if (path === "/api/state") {
            return statePayload;
        }
        if (path === "/api/research/state") {
            return researchStatePayload;
        }
        throw new Error(`unexpected path: ${path}`);
    };

    const ctx = {
        api,
        els,
        localStorageKeys,
        providerModelFeature: {
            populateProviderAndModelSelect: (providers, models) => {
                calls.providerPopulate.push({ providers, models });
            },
        },
        uiLayoutFeature: {
            setActiveTab: (tab) => calls.uiLayout.activeTab.push(tab),
            setActiveCvTab: (tab) => calls.uiLayout.activeCvTab.push(tab),
            setActiveResearchInputTab: (tab) => calls.uiLayout.activeResearchInputTab.push(tab),
            setActiveLogTab: (tab) => calls.uiLayout.activeLogTab.push(tab),
            setActiveResearchOutputTab: (tab) => calls.uiLayout.activeResearchOutputTab.push(tab),
        },
        researchFeature: {
            fetchResearchStatus: async () => researchStatusPayload,
            waitForResearchCompletion: async () => ({
                success: true,
                elapsedSeconds: 1,
                command: [],
            }),
        },
        setStatus: (message, isError = false) => calls.setStatus.push({ message, isError }),
        applyFilesToEditors: (files) => calls.applyFilesToEditors.push(files),
        updateDiskSnapshot: (files) => calls.updateDiskSnapshot.push(files),
        applyCvOutputState: (payload) => calls.applyCvOutputState.push(payload),
        renderResearchState: (payload) => calls.renderResearchState.push(payload),
        hasLocalDraft: () => Boolean(options.hasLocalDraft),
        loadLocalDraft: (diskFiles) => calls.loadLocalDraft.push(diskFiles),
        writeDraftToLocalStorage: () => {
            calls.writeDraftToLocalStorage += 1;
        },
        syncDirtyIndicators: () => {
            calls.syncDirtyIndicators += 1;
        },
        setRunLogOutput: (text) => calls.setRunLogOutput.push(text),
        summarizeRun: (run) => `run:${run.id}`,
        summarizeResearchOutput: (run) => `research:${run.success}`,
        setResearchOutput: (text) => calls.setResearchOutput.push(text),
        setResearchCommandOutput: (command) => calls.setResearchCommandOutput.push(command),
        setResearchStatus: (message, isError = false) =>
            calls.setResearchStatus.push({ message, isError }),
        setResearchRunning: (running) => calls.setResearchRunning.push(running),
        updatePreview: () => {
            calls.updatePreview += 1;
        },
        refreshTailoredOutput: async () => {
            calls.refreshTailoredOutput += 1;
        },
    };

    return { ctx, calls, localStorageKeys, statePayload };
}

test("app initialization uses disk state when no local draft and restores saved tabs", async () => {
    const { ctx, calls, localStorageKeys, statePayload } = createHarness({ hasLocalDraft: false });

    localStorage.setItem(localStorageKeys.active_tab, "logs");
    localStorage.setItem(localStorageKeys.active_cv_tab, "tailored");
    localStorage.setItem(localStorageKeys.active_research_input_tab, "prompt");
    localStorage.setItem(localStorageKeys.active_log_tab, "debug");
    localStorage.setItem(localStorageKeys.research_output_tab, "command");

    const feature = createAppInitializationFeature(ctx);
    await feature.initialize();

    assert.equal(calls.writeDraftToLocalStorage, 1);
    assert.equal(calls.loadLocalDraft.length, 0);
    assert.equal(calls.syncDirtyIndicators, 1);

    assert.deepEqual(calls.providerPopulate.length, 1);
    assert.deepEqual(calls.applyFilesToEditors, [statePayload.files]);
    assert.deepEqual(calls.updateDiskSnapshot, [statePayload.files]);
    assert.deepEqual(calls.renderResearchState.length, 1);

    assert.deepEqual(calls.uiLayout.activeTab, ["logs"]);
    assert.deepEqual(calls.uiLayout.activeCvTab, ["tailored"]);
    assert.deepEqual(calls.uiLayout.activeResearchInputTab, ["prompt"]);
    assert.deepEqual(calls.uiLayout.activeLogTab, ["debug"]);
    assert.deepEqual(calls.uiLayout.activeResearchOutputTab, ["command"]);

    assert.equal(calls.updatePreview, 1);
    assert.equal(calls.refreshTailoredOutput, 1);

    assert.equal(calls.setRunLogOutput.at(-1), "run:run1");
    assert.equal(calls.setResearchStatus.at(-1).message, "Idle.");
    assert.deepEqual(calls.setResearchCommandOutput.at(-1), []);
    assert.equal(calls.setStatus.at(0).message, "Loading editor state...");
    assert.equal(calls.setStatus.at(1).message, "Loaded from disk.");
});

test("app initialization passes the server theme list to the theme feature", async () => {
    const { ctx, statePayload } = createHarness({ hasLocalDraft: false });
    statePayload.themes = ["default", "compact"];
    const populated = [];
    ctx.themeFeature = { populateThemeSelect: (themes) => populated.push(themes) };

    await createAppInitializationFeature(ctx).initialize();

    assert.deepEqual(populated, [["default", "compact"]]);
});

test("app initialization prefers local draft and falls back to default tabs when missing", async () => {
    const { ctx, calls } = createHarness({ hasLocalDraft: true });

    const feature = createAppInitializationFeature(ctx);
    await feature.initialize();

    assert.equal(calls.writeDraftToLocalStorage, 0);
    assert.equal(calls.loadLocalDraft.length, 1);
    assert.equal(calls.syncDirtyIndicators, 1);

    assert.deepEqual(calls.uiLayout.activeTab, ["cv"]);
    assert.deepEqual(calls.uiLayout.activeCvTab, ["cv"]);
    assert.deepEqual(calls.uiLayout.activeResearchInputTab, ["query"]);
    assert.deepEqual(calls.uiLayout.activeLogTab, ["run"]);
    assert.deepEqual(calls.uiLayout.activeResearchOutputTab, ["console"]);

    assert.equal(
        calls.setStatus.some(
            (entry) => entry.message === "Loaded browser draft. Use per-tab Save to write to disk.",
        ),
        true,
    );
});

test("app initialization reports startup failure when state request errors", async () => {
    const { ctx, calls } = createHarness({
        apiError: { path: "/api/state", message: "state down" },
    });

    const feature = createAppInitializationFeature(ctx);
    await feature.initialize();

    assert.equal(calls.providerPopulate.length, 0);
    assert.equal(calls.applyFilesToEditors.length, 0);
    assert.equal(calls.renderResearchState.length, 0);

    assert.equal(calls.setStatus.at(0).message, "Loading editor state...");
    assert.equal(calls.setStatus.at(-1).message, "Initialization failed: state down");
    assert.equal(calls.setStatus.at(-1).isError, true);
});
