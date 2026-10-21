import test from "node:test";
import assert from "node:assert/strict";

import { createRoleRunsFeature } from "../role-runs-feature.js";

function fakeOption() {
    return { value: "", textContent: "", disabled: false };
}

const RUNS = [
    { id: 4, success: 0, isCurrent: 0, provider: "gemini", model: "", steeringText: "", startedAt: "2026-10-21T10:00" },
    { id: 3, success: 1, isCurrent: 1, provider: "claude", model: "sonnet", steeringText: "AI", finishedAt: "2026-10-20T09:00" },
    { id: 2, success: 1, isCurrent: 0, provider: null, model: null, steeringText: null, finishedAt: "2026-10-19T09:00" },
];

function createHarness({ runs = RUNS, selectedTheme = "default", activeRoleId = 7 } = {}) {
    global.document = { createElement: fakeOption };
    const calls = { api: [], sources: [], updatePreview: 0 };
    const state = { activeRoleId, cvRuns: [], selectedCvRunId: null, selectedTheme };
    const els = {
        runSelect: {
            value: "",
            options: [],
            replaceChildren() {
                this.options = [];
            },
            appendChild(opt) {
                this.options.push(opt);
            },
        },
        tailoredViewer: { value: "" },
        tailoredTitle: { textContent: "" },
    };
    const api = async (path) => {
        calls.api.push(path);
        if (path.endsWith("/runs")) {
            return { cvRuns: runs, researchRuns: [] };
        }
        const id = Number(path.split("/").pop());
        return { run: { id, rawOutput: "raw", modelJson: { name: "Robin" } } };
    };
    const feature = createRoleRunsFeature({
        state,
        els,
        api,
        setStatus: () => {},
        setCvRunSource: (source) => calls.sources.push(source),
        updatePreview: () => {
            calls.updatePreview += 1;
        },
        formatDateTime: (value) => `@${value}`,
    });
    return { feature, state, els, calls };
}

test("loadRuns picks the current run and previews it in the default theme", async () => {
    const { feature, state, els, calls } = createHarness();

    await feature.loadRuns(7);

    assert.equal(state.selectedCvRunId, 3);
    assert.equal(els.runSelect.value, "3");
    assert.equal(els.runSelect.options[0].disabled, true);
    assert.equal(els.runSelect.options[1].textContent, "#3 · @2026-10-20T09:00 · claude/sonnet · 🧭 · current");
    assert.deepEqual(calls.sources.at(-1), {
        url: "/api/roles/7/runs/cv/3/cv.pdf?theme=",
        docxUrl: "/api/roles/7/runs/cv/3/cv.docx",
        label: "run #3",
        steering: "AI",
        generatedAt: "2026-10-20T09:00",
    });
    assert.equal(els.tailoredViewer.value, JSON.stringify({ name: "Robin" }, null, 2));
    assert.equal(els.tailoredTitle.textContent, "Run #3 model output (read-only)");
});

test("loadRuns selects a requested successful run, and the theme goes in the URL", async () => {
    const { feature, state, calls } = createHarness({ selectedTheme: "compact" });

    await feature.loadRuns(7, { selectRunId: 2 });

    assert.equal(state.selectedCvRunId, 2);
    assert.equal(calls.sources.at(-1).url, "/api/roles/7/runs/cv/2/cv.pdf?theme=compact");
});

test("a role with no runs shows an empty preview and picker", async () => {
    const { feature, state, els, calls } = createHarness({ runs: [] });

    await feature.loadRuns(7);

    assert.equal(state.selectedCvRunId, null);
    assert.equal(els.runSelect.options[0].textContent, "No runs yet");
    assert.equal(calls.sources.at(-1).url, null);
    assert.match(els.tailoredViewer.value, /No runs yet/);
});

test("picking a run previews it", async () => {
    const { feature, state, els, calls } = createHarness();
    await feature.loadRuns(7);

    els.runSelect.value = "2";
    await feature.handleRunSelectChanged();

    assert.equal(state.selectedCvRunId, 2);
    assert.equal(calls.sources.at(-1).label, "run #2");
});

test("file mode leaves the Tailored tab to the file behaviour", async () => {
    const { feature } = createHarness({ activeRoleId: null });

    assert.equal(await feature.refreshTailoredOutput(), false);
});

test("afterCvRun reloads the history and shows the new run", async () => {
    const { feature, state } = createHarness();

    await feature.afterCvRun(7, { runId: 2, success: true });
    assert.equal(state.selectedCvRunId, 2);

    state.selectedCvRunId = null;
    await feature.afterCvRun(8, { runId: 3 });
    assert.equal(state.selectedCvRunId, null);
});
