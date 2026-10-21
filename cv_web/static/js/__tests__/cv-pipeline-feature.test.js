import test from "node:test";
import assert from "node:assert/strict";

import { createCvPipelineFeature } from "../cv-pipeline-feature.js";

function createContext(overrides = {}) {
    const calls = {
        setRunning: [],
        startRunStatusTimer: [],
        stopRunStatusTimer: 0,
        setRunLogOutput: [],
        setStatus: [],
        updateDiskSnapshot: [],
        applyCvOutputState: [],
        updatePreviewCacheBuster: 0,
        refreshTailoredOutput: 0,
        refreshLogs: 0,
    };

    const ctx = {
        api: async () => {
            throw new Error("api not stubbed");
        },
        currentFiles: () => ({
            cv: "cv",
            prompt: "prompt",
            research_prompt: "",
            jobspec: "job",
            env: "",
        }),
        writeDraftToLocalStorage: () => {},
        state: { selectedProvider: "gemini", selectedModel: "model-x" },
        setRunning: (value) => calls.setRunning.push(value),
        startRunStatusTimer: (message) => calls.startRunStatusTimer.push(message),
        stopRunStatusTimer: () => {
            calls.stopRunStatusTimer += 1;
        },
        setRunLogOutput: (text) => calls.setRunLogOutput.push(text),
        setStatus: (message, isError = false) => calls.setStatus.push({ message, isError }),
        updateDiskSnapshot: (files) => calls.updateDiskSnapshot.push(files),
        applyCvOutputState: (payload) => calls.applyCvOutputState.push(payload),
        updatePreviewCacheBuster: () => {
            calls.updatePreviewCacheBuster += 1;
        },
        refreshTailoredOutput: async () => {
            calls.refreshTailoredOutput += 1;
        },
        refreshLogs: async () => {
            calls.refreshLogs += 1;
        },
        summarizeRun: (run) => `run:${run.kind}:${run.success}`,
        ...overrides,
    };

    return { ctx, calls };
}

test("cv pipeline runPipeline success path updates state and refreshes outputs", async () => {
    const kickoffRun = { kind: "format", success: true, elapsedSeconds: 2, running: false };
    const finalRun = { kind: "format", success: true, elapsedSeconds: 2, running: false };

    const { ctx, calls } = createContext({
        api: async (path) => {
            if (path === "/api/run/format") {
                return { run: kickoffRun };
            }
            if (path === "/api/run/status") {
                return { running: false, run: finalRun };
            }
            if (path === "/api/state") {
                return { files: { cv: "updated" } };
            }
            throw new Error(`unexpected path: ${path}`);
        },
    });

    const feature = createCvPipelineFeature(ctx);
    await feature.runPipeline("format");

    assert.deepEqual(calls.setRunning, [true, false]);
    assert.deepEqual(calls.startRunStatusTimer, ["Running formatting only..."]);
    assert.ok(calls.stopRunStatusTimer >= 1);
    assert.equal(calls.updatePreviewCacheBuster, 1);
    assert.equal(calls.refreshTailoredOutput, 1);
    assert.equal(calls.refreshLogs, 1);
    assert.deepEqual(calls.updateDiskSnapshot, [{ cv: "updated" }]);
    assert.equal(calls.applyCvOutputState.length, 1);
    assert.equal(calls.setStatus.at(-1).message, "Run complete (2s).");
    assert.equal(calls.setStatus.at(-1).isError, false);
});

test("cv pipeline runPipeline sends the selected theme", async () => {
    const bodies = [];
    const { ctx } = createContext({
        state: { selectedProvider: "gemini", selectedModel: "", selectedTheme: "compact" },
        api: async (path, options) => {
            if (path === "/api/run/format") {
                bodies.push(JSON.parse(options.body));
                return {};
            }
            if (path === "/api/run/status") {
                return { running: false, run: null };
            }
            return {};
        },
    });

    await createCvPipelineFeature(ctx).runPipeline("format");

    assert.equal(bodies[0].selectedTheme, "compact");
});

test("cv pipeline runPipeline failure path emits error status", async () => {
    const kickoffRun = { kind: "full", success: false, elapsedSeconds: 5, running: false };
    const finalRun = { kind: "full", success: false, elapsedSeconds: 5, running: false };

    const { ctx, calls } = createContext({
        api: async (path) => {
            if (path === "/api/run/full") {
                return { run: kickoffRun };
            }
            if (path === "/api/run/status") {
                return { running: false, run: finalRun };
            }
            if (path === "/api/state") {
                return { files: {} };
            }
            throw new Error(`unexpected path: ${path}`);
        },
    });

    const feature = createCvPipelineFeature(ctx);
    await feature.runPipeline("full");

    const last = calls.setStatus.at(-1);
    assert.equal(last.message, "Run failed. Open logs for details.");
    assert.equal(last.isError, true);
});
