import test from "node:test";
import assert from "node:assert/strict";

import { createAppEventBindingsFeature } from "../app-event-bindings-feature.js";

function createElement(dataset = {}) {
    const listeners = new Map();
    return {
        dataset,
        addEventListener(event, handler) {
            if (!listeners.has(event)) {
                listeners.set(event, []);
            }
            listeners.get(event).push(handler);
        },
        trigger(event) {
            const handlers = listeners.get(event) || [];
            handlers.forEach((handler) => handler());
        },
    };
}

function createHarness(overrides = {}) {
    const calls = {
        runPipeline: [],
        restartServerFromWeb: 0,
        onResearchPrimaryAction: 0,
        formatResearchPdf: 0,
        resetResearchPrompt: 0,
        copyResearchOutputToClipboard: 0,
        refreshLogs: 0,
        loadSelectedDebugLog: 0,
        setActiveTab: [],
        setActiveCvTab: [],
        setActiveResearchInputTab: [],
        setActiveLogTab: [],
        setActiveResearchOutputTab: [],
        saveSingleFile: [],
        loadSingleFile: [],
        handleModelSelectChanged: 0,
        handleProviderSelectChanged: 0,
        pointerMoveHandlers: 0,
        pointerUpHandlers: 0,
        pointerCancelHandlers: 0,
    };

    const els = {
        runFormatBtn: createElement(),
        runFullBtn: createElement(),
        restartServerBtn: createElement(),
        runResearchBtn: createElement(),
        formatResearchBtn: createElement(),
        resetResearchPromptBtn: createElement(),
        copyResearchOutputBtn: createElement(),
        refreshLogsBtn: createElement(),
        logSelect: createElement(),
        tabButtons: [createElement({ tab: "cv" }), createElement({ tab: "logs" })],
        cvTabButtons: [createElement({ cvTab: "cv" }), createElement({ cvTab: "tailored" })],
        researchInputTabButtons: [
            createElement({ researchInputTab: "query" }),
            createElement({ researchInputTab: "jobspec" }),
        ],
        logTabButtons: [createElement({ logTab: "run" }), createElement({ logTab: "debug" })],
        researchOutputTabButtons: [
            createElement({ researchOutputTab: "console" }),
            createElement({ researchOutputTab: "command" }),
        ],
        fileSaveButtons: [createElement({ file: "cv" }), createElement({ file: "prompt" })],
        fileLoadButtons: [createElement({ file: "env" }), createElement({ file: "jobspec" })],
        paneSplitter: createElement(),
        researchSplitters: [createElement({ researchSplitter: "top" })],
        modelSelect: createElement(),
        providerSelect: createElement(),
        ...overrides.els,
    };

    const ctx = {
        els,
        cvPipelineFeature: {
            runPipeline: (kind) => calls.runPipeline.push(kind),
        },
        appOperationsFeature: {
            restartServerFromWeb: () => {
                calls.restartServerFromWeb += 1;
            },
            saveSingleFile: (fileKey) => calls.saveSingleFile.push(fileKey),
            loadSingleFile: (fileKey) => calls.loadSingleFile.push(fileKey),
        },
        researchFeature: {
            onResearchPrimaryAction: () => {
                calls.onResearchPrimaryAction += 1;
            },
            formatResearchPdf: () => {
                calls.formatResearchPdf += 1;
            },
            resetResearchPrompt: () => {
                calls.resetResearchPrompt += 1;
            },
            copyResearchOutputToClipboard: () => {
                calls.copyResearchOutputToClipboard += 1;
            },
        },
        logsFeature: {
            refreshLogs: () => {
                calls.refreshLogs += 1;
            },
            loadSelectedDebugLog: () => {
                calls.loadSelectedDebugLog += 1;
            },
        },
        uiLayoutFeature: {
            setActiveTab: (name) => calls.setActiveTab.push(name),
            setActiveCvTab: (name) => calls.setActiveCvTab.push(name),
            setActiveResearchInputTab: (name) => calls.setActiveResearchInputTab.push(name),
            setActiveLogTab: (name) => calls.setActiveLogTab.push(name),
            setActiveResearchOutputTab: (name) => calls.setActiveResearchOutputTab.push(name),
            onSplitterPointerDown: () => {},
            onResearchSplitterPointerDown: () => {},
            onSplitterPointerMove: () => {},
            onSplitterPointerUp: () => {},
        },
        providerModelFeature: {
            handleModelSelectChanged: () => {
                calls.handleModelSelectChanged += 1;
            },
            handleProviderSelectChanged: () => {
                calls.handleProviderSelectChanged += 1;
            },
        },
    };

    global.window = {
        addEventListener(event, _handler) {
            if (event === "pointermove") {
                calls.pointerMoveHandlers += 1;
            }
            if (event === "pointerup") {
                calls.pointerUpHandlers += 1;
            }
            if (event === "pointercancel") {
                calls.pointerCancelHandlers += 1;
            }
        },
    };

    return { ctx, els, calls };
}

test("app-event-bindings wires core click/change actions", () => {
    const { ctx, els, calls } = createHarness();

    const feature = createAppEventBindingsFeature(ctx);
    feature.bindEventHandlers();

    els.runFormatBtn.trigger("click");
    els.runFullBtn.trigger("click");
    els.restartServerBtn.trigger("click");
    els.runResearchBtn.trigger("click");
    els.formatResearchBtn.trigger("click");
    els.resetResearchPromptBtn.trigger("click");
    els.copyResearchOutputBtn.trigger("click");
    els.refreshLogsBtn.trigger("click");
    els.logSelect.trigger("change");
    els.modelSelect.trigger("change");
    els.providerSelect.trigger("change");

    assert.deepEqual(calls.runPipeline, ["format", "full"]);
    assert.equal(calls.restartServerFromWeb, 1);
    assert.equal(calls.onResearchPrimaryAction, 1);
    assert.equal(calls.formatResearchPdf, 1);
    assert.equal(calls.resetResearchPrompt, 1);
    assert.equal(calls.copyResearchOutputToClipboard, 1);
    assert.equal(calls.refreshLogs, 1);
    assert.equal(calls.loadSelectedDebugLog, 1);
    assert.equal(calls.handleModelSelectChanged, 1);
    assert.equal(calls.handleProviderSelectChanged, 1);
});

test("app-event-bindings wires the theme selector when present", () => {
    const { ctx, els } = createHarness();
    let themeChanges = 0;
    els.themeSelect = createElement();
    ctx.themeFeature = {
        handleThemeSelectChanged: () => {
            themeChanges += 1;
        },
    };

    createAppEventBindingsFeature(ctx).bindEventHandlers();
    els.themeSelect.trigger("change");

    assert.equal(themeChanges, 1);
});

test("app-event-bindings wires the steering editor and checkbox", () => {
    const { ctx, els } = createHarness();
    const calls = { input: 0, toggle: 0 };
    els.steeringEditor = createElement();
    els.steerCheckbox = createElement();
    ctx.steeringFeature = {
        handleSteeringInput: () => {
            calls.input += 1;
        },
        handleSteerCheckboxChanged: () => {
            calls.toggle += 1;
        },
    };

    createAppEventBindingsFeature(ctx).bindEventHandlers();
    els.steeringEditor.trigger("input");
    els.steerCheckbox.trigger("change");

    assert.deepEqual(calls, { input: 1, toggle: 1 });
});

test("app-event-bindings maps tab and file button datasets", () => {
    const { ctx, els, calls } = createHarness();

    const feature = createAppEventBindingsFeature(ctx);
    feature.bindEventHandlers();

    els.tabButtons[1].trigger("click");
    els.cvTabButtons[1].trigger("click");
    els.researchInputTabButtons[1].trigger("click");
    els.logTabButtons[1].trigger("click");
    els.researchOutputTabButtons[1].trigger("click");
    els.fileSaveButtons[0].trigger("click");
    els.fileLoadButtons[1].trigger("click");

    assert.deepEqual(calls.setActiveTab, ["logs"]);
    assert.deepEqual(calls.setActiveCvTab, ["tailored"]);
    assert.deepEqual(calls.setActiveResearchInputTab, ["jobspec"]);
    assert.deepEqual(calls.setActiveLogTab, ["debug"]);
    assert.deepEqual(calls.setActiveResearchOutputTab, ["command"]);
    assert.deepEqual(calls.saveSingleFile, ["cv"]);
    assert.deepEqual(calls.loadSingleFile, ["jobspec"]);
});

test("app-event-bindings handles optional controls and pane splitters", () => {
    const { ctx, calls } = createHarness({
        els: {
            restartServerBtn: null,
            runResearchBtn: null,
            formatResearchBtn: null,
            resetResearchPromptBtn: null,
            copyResearchOutputBtn: null,
        },
    });

    const feature = createAppEventBindingsFeature(ctx);
    feature.bindEventHandlers();

    assert.equal(calls.pointerMoveHandlers, 1);
    assert.equal(calls.pointerUpHandlers, 1);
    assert.equal(calls.pointerCancelHandlers, 1);
});
