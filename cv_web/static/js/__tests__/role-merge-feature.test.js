import test from "node:test";
import assert from "node:assert/strict";

import { createRoleMergeFeature } from "../role-merge-feature.js";

function fakeElement(tag = "div") {
    return {
        tagName: tag,
        children: [],
        textContent: "",
        className: "",
        value: "",
        checked: false,
        hidden: false,
        listeners: {},
        append(...nodes) {
            this.children.push(...nodes);
        },
        appendChild(node) {
            this.children.push(node);
        },
        replaceChildren() {
            this.children = [];
        },
        addEventListener(type, handler) {
            this.listeners[type] = handler;
        },
    };
}

/** Every descendant (depth first) matching a predicate. */
function findAll(root, predicate, found = []) {
    (root.children || []).forEach((child) => {
        if (predicate(child)) {
            found.push(child);
        }
        findAll(child, predicate, found);
    });
    return found;
}

const CHANGES = [
    { key: ["roles", "a"], kind: "entry", heading: "A", status: "changed", diff: "@@ -1 +1 @@\n-old\n+new", accept: true },
    { key: ["roles", "b"], kind: "entry", heading: "B", status: "removed", diff: "-gone", accept: false },
    {
        key: ["roles", "c"],
        kind: "entry",
        heading: "C",
        status: "conflict",
        diff: "-mine\n+theirs",
        current: "## C\nmine",
        accept: false,
    },
];

function createHarness({ changes = CHANGES, baseBehind = false, cvDirty = false, postError = null } = {}) {
    global.document = { createElement: fakeElement };
    const calls = { api: [], status: [], loads: 0 };
    const dialog = Object.assign(fakeElement("dialog"), {
        open: false,
        showModal() {
            this.open = true;
        },
        close() {
            this.open = false;
        },
    });
    const els = {
        mergeDialog: dialog,
        mergeTitle: fakeElement("h2"),
        mergeHint: fakeElement("p"),
        mergeList: fakeElement("ul"),
        mergeError: fakeElement("p"),
    };
    const state = { activeRoleId: 4, diskFiles: { cv: "saved" } };
    const api = async (path, options = {}) => {
        const body = options.body ? JSON.parse(options.body) : null;
        calls.api.push({ path, method: options.method || "GET", body });
        if (!options.method) {
            return { direction: "pull", targetId: 10, sourceId: 20, changes, baseBehind };
        }
        if (postError) {
            throw new Error(postError);
        }
        return { success: true, unchanged: false };
    };
    const feature = createRoleMergeFeature({
        state,
        els,
        api,
        setStatus: (message, isError = false) => calls.status.push({ message, isError }),
        currentFileValues: () => ({ cv: cvDirty ? "edited" : "saved" }),
        loadOpenCv: async () => {
            calls.loads += 1;
        },
    });
    return { feature, els, calls, dialog };
}

test("openMerge lists changes with default ticks and conflict choices", async () => {
    const { feature, els, calls, dialog } = createHarness();
    await feature.openMerge("pull");

    assert.equal(calls.api[0].path, "/api/roles/4/merge?direction=pull");
    assert.equal(dialog.open, true);
    assert.equal(els.mergeTitle.textContent, "Pull from master");
    assert.equal(els.mergeList.children.length, 3);
    assert.match(els.mergeList.children[2].className, /merge-conflict/);
    const checkboxes = findAll(els.mergeList, (node) => node.type === "checkbox");
    assert.deepEqual(
        checkboxes.map((box) => box.checked),
        [true, false],
    );
    const radios = findAll(els.mergeList, (node) => node.type === "radio");
    assert.deepEqual(
        radios.map((radio) => radio.value),
        ["current", "incoming", "edit"],
    );
    const diffLines = findAll(els.mergeList.children[0], (node) => node.className === "diff-add");
    assert.deepEqual(
        diffLines.map((line) => line.textContent),
        ["+new\n"],
    );
});

test("applyMerge needs every conflict resolved, then posts ticks and resolutions", async () => {
    const { feature, els, calls, dialog } = createHarness();
    await feature.openMerge("pull");
    await feature.applyMerge();
    assert.match(els.mergeError.textContent, /1 left/);
    assert.equal(calls.api.length, 1);

    const [, removed] = findAll(els.mergeList, (node) => node.type === "checkbox");
    removed.checked = true;
    const radios = findAll(els.mergeList, (node) => node.type === "radio");
    const edit = radios[2];
    edit.checked = true;
    edit.listeners.change();
    const textarea = findAll(els.mergeList, (node) => node.className === "merge-edit")[0];
    assert.equal(textarea.hidden, false);
    textarea.value = "## C\nboth";
    await feature.applyMerge();

    const post = calls.api[1];
    assert.equal(post.method, "POST");
    assert.deepEqual(post.body, {
        direction: "pull",
        targetId: 10,
        sourceId: 20,
        accept: [
            ["roles", "a"],
            ["roles", "b"],
        ],
        resolutions: [{ key: ["roles", "c"], choice: "edit", text: "## C\nboth" }],
    });
    assert.equal(dialog.open, false);
    assert.equal(calls.loads, 1);
    assert.equal(calls.status.at(-1).message, "Pulled master changes into the role CV.");
});

test("openMerge refuses with unsaved CV edits", async () => {
    const { feature, calls, dialog } = createHarness({ cvDirty: true });
    await feature.openMerge("promote");
    assert.equal(calls.api.length, 0);
    assert.equal(dialog.open, false);
    assert.equal(calls.status[0].isError, true);
});

test("nothing to merge: says so, and a pull still moves a stale base", async () => {
    const promote = createHarness({ changes: [] });
    await promote.feature.openMerge("promote");
    assert.equal(promote.dialog.open, false);
    assert.equal(promote.calls.api.length, 1);
    assert.match(promote.calls.status[0].message, /Nothing to promote/);

    const pull = createHarness({ changes: [], baseBehind: true });
    await pull.feature.openMerge("pull");
    assert.equal(pull.calls.api[1].method, "POST");
    assert.deepEqual(pull.calls.api[1].body.accept, []);
    assert.match(pull.calls.status[0].message, /Nothing to pull/);
});

test("a refused save stays in the dialog with the error", async () => {
    const { feature, els, calls, dialog } = createHarness({
        changes: CHANGES.slice(0, 1),
        postError: "The role or master CV changed since the merge view opened; open it again",
    });
    await feature.openMerge("promote");
    await feature.applyMerge();
    assert.equal(dialog.open, true);
    assert.match(els.mergeError.textContent, /changed since/);
    assert.equal(calls.loads, 0);
    feature.closeMerge();
    assert.equal(dialog.open, false);
});

test("import uses the master import routes and the file hash", async () => {
    global.document = { createElement: fakeElement };
    const calls = [];
    const dialog = Object.assign(fakeElement("dialog"), {
        open: false,
        showModal() {
            this.open = true;
        },
        close() {
            this.open = false;
        },
    });
    const els = {
        mergeDialog: dialog,
        mergeTitle: fakeElement("h2"),
        mergeHint: fakeElement("p"),
        mergeList: fakeElement("ul"),
        mergeError: fakeElement("p"),
    };
    const feature = createRoleMergeFeature({
        state: { activeRoleId: 4, diskFiles: { cv: "" } },
        els,
        api: async (path, options = {}) => {
            calls.push({ path, method: options.method || "GET", body: options.body && JSON.parse(options.body) });
            return options.method
                ? { unchanged: false }
                : { direction: "import", targetId: 7, sourceHash: "abc", changes: CHANGES.slice(0, 1) };
        },
        setStatus: () => {},
        currentFileValues: () => ({ cv: "" }),
        loadOpenCv: async () => {},
    });
    await feature.openMerge("import");
    assert.equal(els.mergeTitle.textContent, "Import input/CV.md as master");
    await feature.applyMerge();
    assert.deepEqual(calls[0], { path: "/api/master/import", method: "GET", body: undefined });
    assert.deepEqual(calls[1], {
        path: "/api/master/import",
        method: "POST",
        body: { targetId: 7, sourceHash: "abc", accept: [["roles", "a"]], resolutions: [] },
    });
});
