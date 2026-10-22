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

test("research run in role mode starts a role run without sending files", async () => {
    const posted = [];
    const after = [];
    const { ctx, calls } = createContext({
        getActiveRoleId: () => 5,
        saveRoleEditsBeforeRun: async () => posted.push("save"),
        afterRoleResearchRun: async (roleId, run) => after.push([roleId, run.runId]),
        api: async (path, options = {}) => {
            if (path === "/api/roles/5/runs/research") {
                posted.push(JSON.parse(options.body));
                return { run: { elapsedSeconds: 0, success: null } };
            }
            if (path === "/api/roles/5/runs") {
                return { researchRuns: [] };
            }
            if (path === "/api/research/status") {
                return { running: false, run: { elapsedSeconds: 4, success: true, runId: 8 } };
            }
            throw new Error(`unexpected ${path}`);
        },
    });
    ctx.els.researchCompanyInput.value = "";
    const feature = createResearchFeature(ctx);

    await feature.runResearch();

    assert.deepEqual(posted, [
        "save",
        {
            selectedProvider: "gemini",
            selectedModel: "gemini-2.5-pro",
            company: null,
            urls: ["https://example.com"],
            dryRun: false,
        },
    ]);
    assert.deepEqual(after, [[5, 8]]);
    assert.equal(calls.renderResearchState.length, 0);
    assert.deepEqual(calls.setResearchStatus.at(-1), { message: "Research complete (4s).", isError: false });
});

/**
 * Role-mode context: a stubbed role run API and recorded preview sources.
 * @param {any} runs `researchRuns` for role 5.
 * @param {Record<number, any>} fullRuns Full runs by id.
 */
function createRoleContext(runs, fullRuns = {}, overrides = {}) {
    const sources = [];
    const builtQuery = [];
    let activeRoleId = 5;
    const { ctx, calls } = createContext({
        getActiveRoleId: () => activeRoleId,
        setResearchRunSource: (source) => sources.push(source),
        setResearchBuiltQueryOutput: (text) => builtQuery.push(text),
        api: async (path) => {
            calls.api.push(path);
            if (path === "/api/roles/5/runs") {
                return { cvRuns: [], researchRuns: runs };
            }
            const match = path.match(/^\/api\/roles\/5\/runs\/research\/(\d+)$/);
            if (match) {
                return { run: fullRuns[Number(match[1])] };
            }
            throw new Error(`unexpected ${path}`);
        },
        ...overrides,
    });
    return { ctx, calls, sources, builtQuery, setActiveRoleId: (id) => (activeRoleId = id) };
}

test("role research shows the current run's markdown and its PDF route", async () => {
    const { ctx, calls, sources, builtQuery } = createRoleContext(
        [
            { id: 9, isCurrent: false, success: false },
            { id: 7, isCurrent: true, success: true },
        ],
        { 7: { id: 7, outputMd: "# Acme\nNotes", outputJson: { promptPreview: "built" }, finishedAt: "2026-10-22T10:00:00Z" } },
    );
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5);

    assert.deepEqual(calls.api, ["/api/roles/5/runs", "/api/roles/5/runs/research/7"]);
    assert.equal(sources.at(-1).url, "/api/roles/5/runs/research/7/research.pdf");
    assert.equal(sources.at(-1).label, "run #7");
    assert.equal(sources.at(-1).generatedAt, "2026-10-22T10:00:00Z");
    assert.equal(calls.setResearchOutput.at(-1), "# Acme\nNotes");
    assert.equal(builtQuery.at(-1), "built");
    assert.equal(calls.updatePreviewCacheBuster, 1);
});

test("role research with a dry run as current shows no PDF and the dry-run message", async () => {
    const { ctx, calls, sources } = createRoleContext([{ id: 3, isCurrent: true, success: true }], {
        3: { id: 3, outputMd: "", dryRun: 1, outputJson: { output: "[dry-run] prompt built successfully" } },
    });
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5);

    assert.equal(sources.at(-1).url, null);
    assert.equal(sources.at(-1).placeholder, "Run #3 has no output (dry run).");
    assert.equal(calls.setResearchOutput.at(-1), "[dry-run] prompt built successfully");
});

test("role research with no current run, or no role, shows an empty state, not output/ files", async () => {
    const { ctx, calls, sources } = createRoleContext([{ id: 2, isCurrent: false, success: false }]);
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5);
    assert.equal(sources.at(-1).url, null);
    assert.match(sources.at(-1).placeholder, /No research runs yet/);
    assert.match(calls.setResearchOutput.at(-1), /No research runs yet/);

    await feature.loadRoleResearch(null);
    assert.equal(sources.at(-1).url, null);
    assert.equal(sources.at(-1).placeholder, "No role yet: add one with +");
    assert.deepEqual(calls.api, ["/api/roles/5/runs"]);
    assert.equal(calls.renderResearchState.length, 0);
});

test("role research ignores a reply for a role that is no longer active", async () => {
    const { ctx, calls, sources, setActiveRoleId } = createRoleContext([{ id: 7, isCurrent: true }], {
        7: { id: 7, outputMd: "old role" },
    });
    const feature = createResearchFeature(ctx);
    setActiveRoleId(6);

    await feature.loadRoleResearch(5);

    assert.equal(sources.length, 0);
    assert.equal(calls.setResearchOutput.length, 0);
});

test("a failed role research run keeps its log in the console and still refreshes the preview", async () => {
    const { ctx, calls, sources } = createRoleContext([{ id: 7, isCurrent: true, success: true }], {
        7: { id: 7, outputMd: "previous research" },
    });
    const baseApi = ctx.api;
    ctx.api = async (path, options) => {
        if (path === "/api/roles/5/runs/research") {
            return { run: { elapsedSeconds: 0, success: null } };
        }
        if (path === "/api/research/status") {
            return { running: false, run: { elapsedSeconds: 2, success: false, output: "boom" } };
        }
        return baseApi(path, options);
    };
    const feature = createResearchFeature(ctx);

    await feature.runResearch();

    assert.equal(calls.setResearchOutput.at(-1), "research:2:false");
    assert.equal(sources.at(-1).url, "/api/roles/5/runs/research/7/research.pdf");
    assert.deepEqual(calls.setResearchStatus.at(-1), { message: "Research run failed.", isError: true });
});

/** A select stub that records its options. */
function fakeSelect() {
    return {
        value: "",
        options: [],
        replaceChildren() {
            this.options = [];
        },
        appendChild(opt) {
            this.options.push(opt);
        },
    };
}

const RESEARCH_RUNS = [
    { id: 9, success: 0, isCurrent: 0, dryRun: 0, provider: "gemini", model: "", company: "Later", startedAt: "2026-10-22T11:00" },
    { id: 8, success: 1, isCurrent: 1, dryRun: 0, provider: "claude", model: "sonnet", company: "Acme", urlsJson: ["https://a.example", "https://b.example"], finishedAt: "2026-10-22T10:00" },
    { id: 7, success: 1, isCurrent: 0, dryRun: 1, provider: "gemini", model: null, company: null, urlsJson: [], finishedAt: "2026-10-21T10:00" },
];

test("role research fills the run picker; failed runs can't be picked", async () => {
    global.document = { createElement: () => ({ value: "", textContent: "", disabled: false }) };
    const { ctx } = createRoleContext(RESEARCH_RUNS, { 8: { id: 8, outputMd: "md" } }, {
        formatDateTime: (iso) => `t(${iso})`,
    });
    ctx.state.researchRuns = [];
    ctx.els.researchRunSelect = fakeSelect();
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5);

    const labels = ctx.els.researchRunSelect.options.map((opt) => opt.textContent);
    assert.deepEqual(labels, [
        "#9 · t(2026-10-22T11:00) · gemini · ✗",
        "#8 · t(2026-10-22T10:00) · claude/sonnet · ✓ · current",
        "#7 · t(2026-10-21T10:00) · gemini · ✓ · dry run",
    ]);
    assert.deepEqual(ctx.els.researchRunSelect.options.map((opt) => opt.disabled), [true, false, false]);
    assert.equal(ctx.els.researchRunSelect.value, "8");
});

test("role research prefills company and URLs from the current run", async () => {
    const { ctx } = createRoleContext(RESEARCH_RUNS, { 8: { id: 8, outputMd: "md" } });
    ctx.state.roles = [{ id: 5, company: "Role Co" }];
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5);

    assert.equal(ctx.els.researchCompanyInput.value, "Acme");
    assert.equal(ctx.els.researchUrlsInput.value, "https://a.example\nhttps://b.example");
});

test("role research company falls back to the role's when the run or role has none", async () => {
    const { ctx } = createRoleContext([{ ...RESEARCH_RUNS[2], isCurrent: 1 }], { 7: { id: 7, outputMd: "" } });
    ctx.state.roles = [{ id: 5, company: "Role Co" }];
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5);
    assert.equal(ctx.els.researchCompanyInput.value, "Role Co");
    assert.equal(ctx.els.researchUrlsInput.value, "");

    const noRuns = createRoleContext([]);
    noRuns.ctx.state.roles = [{ id: 5, company: "" }];
    await createResearchFeature(noRuns.ctx).loadRoleResearch(5);
    assert.equal(noRuns.ctx.els.researchCompanyInput.value, "");
});

test("a failed role run keeps the inputs it was started with", async () => {
    const { ctx } = createRoleContext(RESEARCH_RUNS, { 8: { id: 8, outputMd: "md" } });
    ctx.els.researchCompanyInput.value = "Typed";
    const feature = createResearchFeature(ctx);

    await feature.loadRoleResearch(5, { keepConsole: true });

    assert.equal(ctx.els.researchCompanyInput.value, "Typed");
});

test("picking a research run makes it current and shows it", async () => {
    global.document = { createElement: () => ({ value: "", textContent: "", disabled: false }) };
    const runs = RESEARCH_RUNS.map((run) => ({ ...run }));
    const posted = [];
    const { ctx, calls, sources } = createRoleContext(runs, {
        7: { id: 7, outputMd: "older research" },
        8: { id: 8, outputMd: "md" },
    });
    const baseApi = ctx.api;
    ctx.api = async (path, options) => {
        if (options && options.method === "POST") {
            posted.push(path);
            runs.forEach((run) => (run.isCurrent = run.id === 7 ? 1 : 0));
            return { success: true };
        }
        return baseApi(path, options);
    };
    ctx.state.researchRuns = [];
    ctx.els.researchRunSelect = fakeSelect();
    const feature = createResearchFeature(ctx);
    ctx.els.researchRunSelect.value = "7";

    await feature.handleResearchRunSelectChanged();

    assert.deepEqual(posted, ["/api/roles/5/runs/research/7/current"]);
    assert.equal(sources.at(-1).url, "/api/roles/5/runs/research/7/research.pdf");
    assert.equal(calls.setResearchOutput.at(-1), "older research");
    assert.equal(ctx.els.researchRunSelect.value, "7");
    assert.deepEqual(calls.setResearchStatus.at(-1), { message: "Showing research run #7.", isError: false });
});

test("a refused run pick reports the error and restores the picker", async () => {
    global.document = { createElement: () => ({ value: "", textContent: "", disabled: false }) };
    const { ctx, calls } = createRoleContext(RESEARCH_RUNS, { 8: { id: 8, outputMd: "md" } });
    ctx.state.researchRuns = RESEARCH_RUNS;
    ctx.els.researchRunSelect = fakeSelect();
    const baseApi = ctx.api;
    ctx.api = async (path, options) => {
        if (options && options.method === "POST") {
            throw new Error("failed runs can't be current");
        }
        return baseApi(path, options);
    };
    const feature = createResearchFeature(ctx);
    ctx.els.researchRunSelect.value = "9";

    await feature.handleResearchRunSelectChanged();

    assert.equal(calls.setResearchStatus.at(-1).isError, true);
    assert.equal(ctx.els.researchRunSelect.value, "8");
});
