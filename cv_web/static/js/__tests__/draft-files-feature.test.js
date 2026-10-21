import test from "node:test";
import assert from "node:assert/strict";

import { createDraftFilesFeature } from "../draft-files-feature.js";

function createLocalStorageMock() {
    const store = new Map();
    return {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
    };
}

const KEYS = ["cv", "prompt", "research_prompt", "jobspec", "env"];
const localStorageKeys = {
    ...Object.fromEntries(KEYS.map((key) => [key, `cvweb.${key}`])),
    research_company: "cvweb.research.company",
    research_urls: "cvweb.research.urls",
};

function createHarness(roleOwned) {
    global.localStorage = createLocalStorageMock();
    const els = {
        cvEditor: { value: "role cv" },
        promptEditor: { value: "prompt" },
        researchPromptEditor: { value: "rp" },
        jobspecEditor: { value: "role job" },
        envEditor: { value: "" },
        researchJobspecEditor: { value: "" },
        researchCvEditor: { value: "" },
        researchCompanyInput: { value: "" },
        researchUrlsInput: { value: "" },
        tabLabels: [],
    };
    const state = { diskFiles: {} };
    const feature = createDraftFilesFeature({
        state,
        els,
        editableFiles: {},
        localStorageKeys,
        setStatus: () => {},
        getRoleOwnedKeys: () => roleOwned,
    });
    return { feature, state, els };
}

test("file mode sends and drafts every editor", () => {
    const { feature } = createHarness([]);

    assert.deepEqual(Object.keys(feature.currentFiles()), KEYS);
    feature.writeDraftToLocalStorage();
    assert.equal(localStorage.getItem("cvweb.cv"), "role cv");
});

test("role mode keeps the role's CV and job spec out of files, drafts and snapshots", () => {
    const { feature, state, els } = createHarness(["cv", "jobspec"]);
    feature.applyRoleFiles({ cv: "role cv", jobspec: "role job" });

    assert.deepEqual(Object.keys(feature.currentFiles()), ["prompt", "research_prompt", "env"]);
    assert.equal(feature.currentFileValues().cv, "role cv");

    feature.writeDraftToLocalStorage();
    assert.equal(localStorage.getItem("cvweb.cv"), null);
    assert.equal(localStorage.getItem("cvweb.prompt"), "prompt");

    feature.applyFilesToEditors({ cv: "disk cv", jobspec: "disk job", prompt: "disk prompt" });
    feature.updateDiskSnapshot({ cv: "disk cv", jobspec: "disk job", prompt: "disk prompt" });
    assert.equal(els.cvEditor.value, "role cv");
    assert.equal(els.jobspecEditor.value, "role job");
    assert.equal(els.promptEditor.value, "disk prompt");
    assert.equal(state.diskFiles.cv, "role cv");
    assert.equal(state.diskFiles.prompt, "disk prompt");
    assert.equal(els.researchCvEditor.value, "role cv");

    localStorage.setItem("cvweb.cv", "old file draft");
    feature.loadLocalDraft({});
    assert.equal(els.cvEditor.value, "role cv");
});
