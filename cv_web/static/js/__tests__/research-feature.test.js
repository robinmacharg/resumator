import test from "node:test";
import assert from "node:assert/strict";

import { createResearchFeature } from "../research-feature.js";

function createContext(overrides = {}) {
    const calls = {
        api: [],
        setStatus: [],
        setResearchStatus: [],
        setResearchOutput: [],
        setResearchCommandOutput: [],
        setResearchRunning: [],
        renderResearchState: [],
        writeDraftToLocalStorage: 0,
        updatePreviewCacheBuster: 0,
    };

    const ctx = {
        state: {
            isResearchRunning: false,
            selectedProvider: "gemini",
            selectedModel: "gemini-2.5-pro",
            activeResearchOutputTab: "console",
        },
        els: {
            researchCompanyInput: { value: "Acme" },
            researchPromptEditor: { value: "Research this company." },
            researchUrlsInput: { value: "https://example.com" },
            researchDryRunCheckbox: { checked: false },
            researchCommandOutput: { value: "" },
            researchBuiltQueryOutput: { textContent: "" },
            researchOutput: { textContent: "" },
        },
        api: async (_path, _options) => {
            throw new Error("api not stubbed");
        },
        currentFiles: () => ({
            cv: "cv",
            prompt: "prompt",
            research_prompt: "rp",
            jobspec: "job",
            env: "",
        }),
        writeDraftToLocalStorage: () => {
            calls.writeDraftToLocalStorage += 1;
        },
        setStatus: (message, isError = false) => calls.setStatus.push({ message, isError }),
        setResearchRunning: (running) => calls.setResearchRunning.push(running),
        updatePreviewCacheBuster: () => {
            calls.updatePreviewCacheBuster += 1;
        },
        updateDiskSnapshot: () => {},
        setResearchStatus: (message, isError = false) =>
            calls.setResearchStatus.push({ message, isError }),
        setResearchOutput: (text) => calls.setResearchOutput.push(text),
        setResearchCommandOutput: (value) => calls.setResearchCommandOutput.push(value),
        renderResearchState: (payload) => calls.renderResearchState.push(payload),
        summarizeResearchOutput: (run) => `research:${run.elapsedSeconds}:${run.success}`,
        ...overrides,
    };

    return { ctx, calls };
}

test("research run validates company name before API call", async () => {
    const { ctx, calls } = createContext();
    ctx.els.researchCompanyInput.value = "   ";

    const feature = createResearchFeature(ctx);
    await feature.runResearch();

    assert.equal(calls.setResearchRunning.length, 0);
    assert.equal(calls.writeDraftToLocalStorage, 0);
    assert.equal(calls.setStatus.at(-1).message, "Company name is required for research run.");
    assert.equal(calls.setStatus.at(-1).isError, true);
    assert.equal(calls.setResearchStatus.at(-1).message, "Company name is required.");
    assert.equal(calls.setResearchStatus.at(-1).isError, true);
});

test("research run validates prompt before API call", async () => {
    const { ctx, calls } = createContext();
    ctx.els.researchPromptEditor.value = "   ";

    const feature = createResearchFeature(ctx);
    await feature.runResearch();

    assert.equal(calls.setResearchRunning.length, 0);
    assert.equal(calls.writeDraftToLocalStorage, 0);
    assert.equal(
        calls.setStatus.at(-1).message,
        "Research prompt is empty. Reset prompt or add content before running.",
    );
    assert.equal(calls.setStatus.at(-1).isError, true);
    assert.equal(calls.setResearchStatus.at(-1).message, "Research prompt is empty.");
});

test("research run success path refreshes state and completes status", async () => {
    const kickoffRun = { success: true, elapsedSeconds: 1, command: ["cmd1"] };
    const finalRun = { success: true, elapsedSeconds: 2, command: ["cmd2"] };

    const { ctx, calls } = createContext({
        api: async (path, options) => {
            calls.api.push({ path, options });
            if (path === "/api/research/run") {
                return { run: kickoffRun };
            }
            if (path === "/api/research/status") {
                return { running: false, run: finalRun };
            }
            if (path === "/api/research/state") {
                return { run: finalRun, reportPath: "output.md" };
            }
            throw new Error(`unexpected path: ${path}`);
        },
    });

    const feature = createResearchFeature(ctx);
    await feature.runResearch();

    assert.deepEqual(calls.setResearchRunning, [true, false]);
    assert.equal(calls.writeDraftToLocalStorage, 1);
    assert.equal(calls.renderResearchState.length, 1);
    assert.equal(calls.updatePreviewCacheBuster, 1);

    const finalResearchStatus = calls.setResearchStatus.at(-1);
    assert.equal(finalResearchStatus.message, "Research complete (2s).");
    assert.equal(finalResearchStatus.isError, false);

    const finalGlobalStatus = calls.setStatus.at(-1);
    assert.equal(finalGlobalStatus.message, "Research run complete.");
    assert.equal(finalGlobalStatus.isError, false);

    assert.ok(calls.api.some((item) => item.path === "/api/research/run"));
    assert.ok(calls.api.some((item) => item.path === "/api/research/status"));
    assert.ok(calls.api.some((item) => item.path === "/api/research/state"));
});
