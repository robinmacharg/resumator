import test from "node:test";
import assert from "node:assert/strict";

import { createCvHistoryFeature } from "../cv-history-feature.js";

function fakeElement(tag = "div") {
    const classes = new Set();
    return {
        tagName: tag,
        dataset: {},
        children: [],
        textContent: "",
        disabled: false,
        listeners: {},
        classList: {
            toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
            contains: (name) => classes.has(name),
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

const VERSIONS = [
    { id: 9, source: "pull", note: null, createdAt: "2026-10-21T10:00:00Z" },
    { id: 4, source: "seed", note: "first", createdAt: "2026-10-20T10:00:00Z" },
];

function createHarness({ cvSource = "role", dirty = false } = {}) {
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
        historyDialog: dialog,
        historyTitle: fakeElement("h2"),
        historyList: fakeElement("ul"),
        historyContent: fakeElement("pre"),
        historyError: fakeElement("p"),
        historyRestoreBtn: fakeElement("button"),
    };
    const api = async (path, options = {}) => {
        calls.api.push({ path, method: options.method || "GET" });
        if (path.endsWith("/restore")) {
            return { unchanged: false };
        }
        const match = path.match(/\/versions\/(\d+)$/);
        if (match) {
            return { version: { id: Number(match[1]), content: `content ${match[1]}` } };
        }
        return { cv: { id: 9 }, versions: VERSIONS };
    };
    const feature = createCvHistoryFeature({
        state: { activeRoleId: 3, cvSource, diskFiles: { cv: "saved" } },
        els,
        api,
        setStatus: (message, isError = false) => calls.status.push({ message, isError }),
        currentFileValues: () => ({ cv: dirty ? "edited" : "saved" }),
        loadOpenCv: async () => {
            calls.loads += 1;
        },
        formatDateTime: (value) => value.slice(0, 10),
    });
    return { feature, els, calls, dialog };
}

test("openHistory lists the open CV's versions, newest marked current", async () => {
    const { feature, els, calls, dialog } = createHarness({ cvSource: "master" });
    await feature.openHistory();
    assert.equal(calls.api[0].path, "/api/master/cv");
    assert.equal(dialog.open, true);
    assert.equal(els.historyTitle.textContent, "Master CV history");
    assert.deepEqual(
        els.historyList.children.map((item) => item.children[0].textContent),
        ["v9 (current) · 2026-10-21 · pulled from master", "v4 · 2026-10-20 · copied from master · first"],
    );
    assert.equal(els.historyRestoreBtn.disabled, true);
});

test("showing and restoring an old version reloads the CV", async () => {
    const { feature, els, calls, dialog } = createHarness();
    await feature.openHistory();
    await feature.showVersion(9);
    assert.equal(els.historyRestoreBtn.disabled, true, "the current version can't be restored");
    await feature.showVersion(4);
    assert.equal(els.historyContent.textContent, "content 4");
    assert.equal(els.historyRestoreBtn.disabled, false);
    assert.equal(els.historyList.children[1].children[0].classList.contains("active"), true);

    await feature.restoreSelected();
    assert.deepEqual(calls.api.at(-1), { path: "/api/roles/3/cv/versions/4/restore", method: "POST" });
    assert.equal(dialog.open, false);
    assert.equal(calls.loads, 1);
    assert.equal(calls.status.at(-1).message, "Restored version 4 as a new version.");
});

test("restore is refused with unsaved CV edits", async () => {
    const { feature, els, calls } = createHarness({ dirty: true });
    await feature.openHistory();
    await feature.showVersion(4);
    await feature.restoreSelected();
    assert.match(els.historyError.textContent, /Save or reload/);
    assert.equal(calls.api.some((call) => call.path.endsWith("/restore")), false);
});
