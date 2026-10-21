import test from "node:test";
import assert from "node:assert/strict";

import { createThemeFeature } from "../theme-feature.js";

const localStorageKeys = { selected_theme: "cvweb.selected_theme" };

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

function createSelectMock() {
    const select = {
        value: "",
        options: [],
        appendChild(node) {
            this.options.push(node);
        },
    };
    Object.defineProperty(select, "innerHTML", {
        set(_value) {
            this.options = [];
        },
    });
    return select;
}

function createHarness({ isRunning = false } = {}) {
    global.localStorage = createLocalStorageMock();
    global.document = {
        createElement() {
            return { value: "", textContent: "" };
        },
    };
    const runs = [];
    const state = { selectedTheme: "default", isRunning };
    const els = { themeSelect: createSelectMock() };
    const feature = createThemeFeature({
        state,
        els,
        localStorageKeys,
        runPipeline: async (kind) => runs.push(kind),
    });
    return { feature, state, els, runs };
}

test("theme populate lists server themes and restores the saved choice", () => {
    const { feature, state, els } = createHarness();
    localStorage.setItem(localStorageKeys.selected_theme, "compact");

    feature.populateThemeSelect(["default", "compact"]);

    assert.deepEqual(
        els.themeSelect.options.map((opt) => [opt.value, opt.textContent]),
        [
            ["default", "Default"],
            ["compact", "Compact"],
        ],
    );
    assert.equal(state.selectedTheme, "compact");
    assert.equal(els.themeSelect.value, "compact");
});

test("theme populate falls back to the first theme when the saved one is gone", () => {
    const { feature, state } = createHarness();
    localStorage.setItem(localStorageKeys.selected_theme, "removed");

    feature.populateThemeSelect(["default", "compact"]);

    assert.equal(state.selectedTheme, "default");
});

test("theme populate offers the default theme when the server sends none", () => {
    const { feature, state, els } = createHarness();

    feature.populateThemeSelect(undefined);

    assert.deepEqual(els.themeSelect.options.map((opt) => opt.value), ["default"]);
    assert.equal(state.selectedTheme, "default");
});

test("theme change persists the choice and re-runs formatting only", async () => {
    const { feature, state, els, runs } = createHarness();
    feature.populateThemeSelect(["default", "compact"]);

    els.themeSelect.value = "compact";
    await feature.handleThemeSelectChanged();

    assert.equal(state.selectedTheme, "compact");
    assert.equal(localStorage.getItem(localStorageKeys.selected_theme), "compact");
    assert.deepEqual(runs, ["format"]);
});

test("theme change during a run is saved but does not start another run", async () => {
    const { feature, els, runs } = createHarness({ isRunning: true });
    feature.populateThemeSelect(["default", "compact"]);

    els.themeSelect.value = "compact";
    await feature.handleThemeSelectChanged();

    assert.equal(localStorage.getItem(localStorageKeys.selected_theme), "compact");
    assert.deepEqual(runs, []);
});

test("theme change in role mode goes to the role handler: no storage write, no format run", async () => {
    const { state, els, runs } = createHarness();
    const handled = [];
    const feature = createThemeFeature({
        state,
        els,
        localStorageKeys,
        runPipeline: async (kind) => runs.push(kind),
        onThemeChanged: (theme) => handled.push(theme) > 0,
    });
    feature.populateThemeSelect(["default", "compact"]);

    els.themeSelect.value = "compact";
    await feature.handleThemeSelectChanged();

    assert.deepEqual(handled, ["compact"]);
    assert.deepEqual(runs, []);
    assert.equal(localStorage.getItem(localStorageKeys.selected_theme), null);
});

test("applyTheme shows a role's theme and falls back to the default for unknown ones", () => {
    const { feature, state, els } = createHarness();
    feature.populateThemeSelect(["default", "compact"]);

    feature.applyTheme("compact");
    assert.equal(state.selectedTheme, "compact");
    assert.equal(els.themeSelect.value, "compact");

    feature.applyTheme("gone");
    assert.equal(state.selectedTheme, "default");
});
