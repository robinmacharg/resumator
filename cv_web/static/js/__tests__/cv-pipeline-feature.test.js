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

test("cv pipeline sends steering with full runs only", async () => {
    const bodies = {};
    const { ctx } = createContext({
        getSteeringRequest: () => ({ enabled: true, text: "AI focus" }),
        api: async (path, options) => {
            if (path === "/api/run/full" || path === "/api/run/format") {
                bodies[path] = JSON.parse(options.body);
                return {};
            }
            if (path === "/api/run/status") {
                return { running: false, run: null };
            }
            return {};
        },
    });
    const feature = createCvPipelineFeature(ctx);

    await feature.runPipeline("full");
    await feature.runPipeline("format");

    assert.deepEqual(bodies["/api/run/full"].steering, { enabled: true, text: "AI focus" });
    assert.equal("steering" in bodies["/api/run/format"], false);
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

test("cv pipeline in role mode saves edits, starts a role run and reloads its history", async () => {
    const order = [];
    let kickoffBody = null;
    const { ctx, calls } = createContext({
        getActiveRoleId: () => 5,
        getSteeringRequest: () => ({ enabled: true, text: "AI focus" }),
        saveRoleEditsBeforeRun: async () => order.push("save"),
        afterRoleCvRun: async (roleId, run) => order.push(`after:${roleId}:${run.runId}`),
        api: async (path, options = {}) => {
            order.push(path);
            if (path === "/api/roles/5/runs/cv") {
                kickoffBody = JSON.parse(options.body);
                return { run: { kind: "role-cv", success: null } };
            }
            if (path === "/api/run/status") {
                return { running: false, run: { kind: "role-cv", success: true, elapsedSeconds: 9, runId: 12 } };
            }
            throw new Error(`unexpected ${path}`);
        },
    });
    const feature = createCvPipelineFeature(ctx);

    await feature.runPipeline("full");

    assert.deepEqual(order, ["save", "/api/roles/5/runs/cv", "/api/run/status", "after:5:12"]);
    assert.deepEqual(kickoffBody, {
        selectedProvider: "gemini",
        selectedModel: "model-x",
        theme: null,
        steering: "AI focus",
    });
    assert.equal(calls.updateDiskSnapshot.length, 0);
    assert.deepEqual(calls.setStatus.at(-1), { message: "Run complete (9s), saved as run #12.", isError: false });
    assert.deepEqual(calls.setRunning, [true, false]);
});

test("cv pipeline in role mode reports the run's error", async () => {
    const { ctx, calls } = createContext({
        getActiveRoleId: () => 5,
        api: async (path) =>
            path === "/api/run/status"
                ? { running: false, run: { success: false, error: "model output invalid" } }
                : { run: null },
    });

    await createCvPipelineFeature(ctx).runPipeline("full");

    assert.deepEqual(calls.setStatus.at(-1), { message: "Run failed: model output invalid", isError: true });
});
