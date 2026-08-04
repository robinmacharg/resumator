import test from "node:test";
import assert from "node:assert/strict";

import { createUiLayoutFeature } from "../ui-layout-feature.js";

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

function createClassList() {
    const set = new Set();
    return {
        toggle(name, active) {
            if (active) {
                set.add(name);
            } else {
                set.delete(name);
            }
        },
        has(name) {
            return set.has(name);
        },
    };
}

function createPanel() {
    return {
        classList: createClassList(),
        style: {
            values: {},
            setProperty(key, value) {
                this.values[key] = value;
            },
        },
    };
}

function createButton(dataset) {
    return {
        dataset,
        classList: createClassList(),
        attributes: {},
        setAttribute(key, value) {
            this.attributes[key] = value;
        },
    };
}

function createContext() {
    const calls = {
        onLogsTabActivated: 0,
        onPreviewUpdate: 0,
        onTailoredTabActivated: 0,
        onTabsChanged: 0,
    };

    const state = {
        activeTab: "cv",
        activeCvTab: "cv",
        activeResearchInputTab: "query",
        activeLogTab: "run",
        activeResearchOutputTab: "console",
        isDraggingSplitter: false,
        isDraggingResearchSplitter: false,
        researchSectionRatios: [1 / 3, 1 / 3, 1 / 3],
    };

    const els = {
        tabPanels: {
            cv: createPanel(),
            logs: createPanel(),
            research: createPanel(),
        },
        tabButtons: [createButton({ tab: "cv" }), createButton({ tab: "logs" })],
        cvTabPanels: {
            cv: createPanel(),
            tailored: createPanel(),
        },
        cvTabButtons: [createButton({ cvTab: "cv" }), createButton({ cvTab: "tailored" })],
        researchInputPanels: {
            query: createPanel(),
            prompt: createPanel(),
        },
        researchInputTabButtons: [
            createButton({ researchInputTab: "query" }),
            createButton({ researchInputTab: "prompt" }),
        ],
        logPanels: {
            run: createPanel(),
            debug: createPanel(),
        },
        logTabButtons: [createButton({ logTab: "run" }), createButton({ logTab: "debug" })],
        researchOutputPanels: {
            console: createPanel(),
            command: createPanel(),
        },
        researchOutputTabButtons: [
            createButton({ researchOutputTab: "console" }),
            createButton({ researchOutputTab: "command" }),
        ],
        paneSplitter: null,
        layout: null,
    };

    const localStorageKeys = {
        active_tab: "active_tab",
        active_cv_tab: "active_cv_tab",
        active_research_input_tab: "active_research_input_tab",
        active_log_tab: "active_log_tab",
        research_output_tab: "research_output_tab",
        research_section_ratios: "research_section_ratios",
    };

    const ctx = {
        state,
        els,
        localStorageKeys,
        onLogsTabActivated: () => {
            calls.onLogsTabActivated += 1;
        },
        onPreviewUpdate: () => {
            calls.onPreviewUpdate += 1;
        },
        onTailoredTabActivated: () => {
            calls.onTailoredTabActivated += 1;
        },
        onTabsChanged: () => {
            calls.onTabsChanged += 1;
        },
    };

    return { ctx, calls, state, els, localStorageKeys };
}

test("ui-layout initializes research ratios from storage and normalizes values", () => {
    global.localStorage = createLocalStorageMock();
    localStorage.setItem("research_section_ratios", JSON.stringify([2, 1, 1]));

    const { ctx, state, els } = createContext();
    const feature = createUiLayoutFeature(ctx);

    feature.initializeResearchSectionRatios();

    assert.deepEqual(state.researchSectionRatios, [0.5, 0.25, 0.25]);
    assert.equal(els.tabPanels.research.style.values["--research-top-size"], "50.0000%");
    assert.equal(els.tabPanels.research.style.values["--research-middle-size"], "25.0000%");
    assert.equal(els.tabPanels.research.style.values["--research-bottom-size"], "25.0000%");
});

test("ui-layout setActiveTab persists state and toggles active classes", () => {
    global.localStorage = createLocalStorageMock();

    const { ctx, calls, state, els, localStorageKeys } = createContext();
    const feature = createUiLayoutFeature(ctx);

    feature.setActiveTab("logs");

    assert.equal(state.activeTab, "logs");
    assert.equal(localStorage.getItem(localStorageKeys.active_tab), "logs");
    assert.equal(calls.onLogsTabActivated, 1);
    assert.equal(calls.onPreviewUpdate, 1);
    assert.equal(els.tabPanels.logs.classList.has("active"), true);
    assert.equal(els.tabPanels.cv.classList.has("active"), false);
});

test("ui-layout CV and research output tabs persist and trigger callbacks", () => {
    global.localStorage = createLocalStorageMock();

    const { ctx, calls, state, localStorageKeys } = createContext();
    const feature = createUiLayoutFeature(ctx);

    feature.setActiveCvTab("tailored");
    feature.setActiveResearchOutputTab("command");

    assert.equal(state.activeCvTab, "tailored");
    assert.equal(localStorage.getItem(localStorageKeys.active_cv_tab), "tailored");
    assert.equal(calls.onTailoredTabActivated, 1);

    assert.equal(state.activeResearchOutputTab, "command");
    assert.equal(localStorage.getItem(localStorageKeys.research_output_tab), "command");
    assert.equal(calls.onTabsChanged, 1);
});
