import test from "node:test";
import assert from "node:assert/strict";

import { createSettingsFeature } from "../settings-feature.js";

// A tiny DOM: enough for the feature's createElement/appendChild/addEventListener/querying by walking.
class FakeElement {
    constructor(tag) {
        this.tag = tag;
        this.children = [];
        this.listeners = {};
        this.value = "";
        this.hidden = false;
        this.textContent = "";
        this.classes = new Set();
        this.dataset = {};
        this.open = false;
        const classes = this.classes;
        this.classList = {
            toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
            add: (name) => classes.add(name),
            remove: (name) => classes.delete(name),
        };
        this.attrs = {};
    }
    appendChild(child) {
        this.children.push(child);
        return child;
    }
    insertBefore(child, before) {
        const index = this.children.indexOf(before);
        this.children.splice(index < 0 ? 0 : index, 0, child);
    }
    removeChild(child) {
        this.children.splice(this.children.indexOf(child), 1);
    }
    setAttribute(name, value) {
        this.attrs[name] = value;
    }
    showModal() {
        this.open = true;
    }
    close() {
        this.open = false;
        this.listeners.close && this.listeners.close();
    }
    addEventListener(name, handler) {
        this.listeners[name] = handler;
    }
    click() {
        return this.listeners.click();
    }
    walk(visit) {
        visit(this);
        this.children.forEach((child) => child.walk(visit));
    }
    find(predicate) {
        const found = [];
        this.walk((node) => predicate(node) && found.push(node));
        return found;
    }
    set textContent(value) {
        this._text = value;
        if (value === "") {
            this.children = [];
        }
    }
    get textContent() {
        return this._text;
    }
}
const fakeDoc = { createElement: (tag) => new FakeElement(tag) };

const GROUPS = [
    {
        id: "global",
        label: "Global",
        settings: [
            { key: "CV_THEME", label: "Theme", kind: "choice", choices: ["default", "compact"], secret: false, isSet: true, value: "compact", advanced: false },
            { key: "CV_FAST_MODE", label: "Fast", kind: "bool", secret: false, isSet: false, value: "", advanced: true },
        ],
    },
    {
        id: "openai",
        label: "OpenAI",
        status: { enabled: false, reason: "OPENAI_API_KEY missing" },
        settings: [
            { key: "OPENAI_API_KEY", label: "API key", kind: "text", secret: true, isSet: false, value: "", advanced: false },
            { key: "OPENAI_MODEL", label: "Model", kind: "text", secret: false, isSet: false, value: "", advanced: false },
        ],
    },
    { id: "other", label: "Other", settings: [{ key: "MY_TOKEN", label: "MY_TOKEN", kind: "text", secret: false, isSet: true, value: "ab…wxyz" }] },
];

const ELEMENT_IDS = [
    "settingsDialog", "settingsOpenBtn", "settingsCloseBtn", "settingsStatus", "settingsImportBtn", "settingsSampleBtn", "settingsEnvBtn", "settingsImportPanel",
    "settingsImportText", "settingsImportFile", "settingsImportMode", "settingsImportPreviewBtn", "settingsImportApplyBtn",
    "settingsImportCloseBtn", "settingsImportResult", "settingsEnvPanel", "settingsEnvText", "settingsEnvRevealBtn",
    "settingsEnvCopyBtn", "settingsEnvDownloadBtn", "settingsEnvCloseBtn",
];

function harness(handlers = {}) {
    const els = Object.fromEntries(ELEMENT_IDS.map((id) => [id, new FakeElement("div")]));
    els.settingsImportMode.value = "merge";
    els.settingsTabButtons = ["global", "providers", "other"].map((name) => {
        const tab = new FakeElement("button");
        tab.dataset.settingsTab = name;
        return tab;
    });
    els.settingsPanels = { global: new FakeElement("div"), providers: new FakeElement("div"), other: new FakeElement("div") };
    els.settingsBody = new FakeElement("div"); // test convenience: the three panels' content, gathered in `body()`
    els.settingsImportPanel.hidden = true;
    els.settingsEnvPanel.hidden = true;
    const calls = [];
    const apiClient = async (path, options = {}) => {
        const body = options.body ? JSON.parse(options.body) : undefined;
        calls.push({ path, method: options.method || "GET", body });
        const handler = handlers[`${options.method || "GET"} ${path}`];
        if (handler) {
            return handler(body);
        }
        if (path === "/api/settings") {
            return { groups: GROUPS };
        }
        throw new Error(`unexpected ${path}`);
    };
    let changed = 0;
    const feature = createSettingsFeature({ els, apiClient, doc: fakeDoc, onSettingsChanged: () => changed++ });
    feature.bind();
    els.settingsBody.find = (predicate) => Object.values(els.settingsPanels).flatMap((panel) => panel.find(predicate));
    return { els, calls, feature, changed: () => changed };
}

const byTag = (root, tag) => root.find((node) => node.tag === tag);
const button = (root, label) => root.find((node) => node.tag === "button" && node.textContent === label)[0];

test("load renders global, provider cards (collapsed when not configured) and other rows", async () => {
    const { els, feature } = harness();
    await feature.load();
    const body = els.settingsBody;
    assert.equal(byTag(els.settingsPanels.global, "section").length, 1);
    assert.equal(byTag(els.settingsPanels.other, "input").length, 2);
    const [card] = byTag(body, "details").filter((n) => n.className === "settings-card");
    assert.equal(card.open, false);
    assert.match(byTag(card, "span").find((n) => /settings-badge/.test(n.className)).textContent, /not configured/);
    assert.equal(byTag(card, "input").find((n) => n.type === "password") !== undefined, true);
    assert.equal(byTag(body, "details").some((n) => n.className === "settings-advanced"), true);
});

test("saving a provider card sends only changed fields", async () => {
    const saved = [];
    const { els, feature, changed } = harness({
        "PUT /api/settings": (body) => {
            saved.push(body);
            return { success: true, groups: GROUPS };
        },
    });
    await feature.load();
    const card = byTag(els.settingsBody, "details").find((n) => n.className === "settings-card");
    const [key, model] = byTag(card, "input");
    key.value = "sk-typed";
    model.value = "";
    await button(card, "Save").click();
    assert.deepEqual(saved, [{ set: { OPENAI_API_KEY: "sk-typed" }, delete: [] }]);
    assert.equal(changed(), 1);
    assert.equal(els.settingsStatus.textContent, "OpenAI saved.");
});

test("saving with nothing changed makes no request", async () => {
    const { els, calls, feature } = harness();
    await feature.load();
    await button(els.settingsBody, "Save").click();
    assert.equal(calls.some((c) => c.method === "PUT"), false);
    assert.equal(els.settingsStatus.textContent, "Nothing to save.");
});

test("Test sends unsaved values as overrides and shows the result", async () => {
    const tested = [];
    const { els, feature } = harness({
        "POST /api/settings/test": (body) => {
            tested.push(body);
            return { ok: true, message: "OK", elapsedSeconds: 0.5, model: "m" };
        },
    });
    await feature.load();
    const card = byTag(els.settingsBody, "details").find((n) => n.className === "settings-card");
    byTag(card, "input")[0].value = "sk-typed";
    await button(card, "Test").click();
    assert.deepEqual(tested, [{ provider: "openai", overrides: { OPENAI_API_KEY: "sk-typed" } }]);
    const result = byTag(card, "span").find((n) => n.className === "settings-test-result");
    assert.equal(result.textContent, "OK (m, 0.5s)");
});

test("import preview is a dry run; apply imports and reloads", async () => {
    const bodies = [];
    const { els, calls, feature } = harness({
        "POST /api/settings/import": (body) => {
            bodies.push(body);
            return { success: true, diff: { added: ["A"], changed: [], unchanged: [], removed: [] } };
        },
    });
    await feature.load();
    els.settingsImportText.value = "A=1";
    await els.settingsImportPreviewBtn.click();
    assert.equal(els.settingsImportResult.textContent, "Preview: 1 added (A)");
    await els.settingsImportApplyBtn.click();
    assert.deepEqual(bodies.map((b) => b.dry_run), [true, false]);
    assert.equal(calls.filter((c) => c.path === "/api/settings" && c.method === "GET").length, 2);
});

test("Load sample fills the import box; View as .env shows masked text and reveal toggles", async () => {
    const { els, calls } = harness({
        "GET /api/settings/sample": () => ({ text: "OPENAI_API_KEY=sk-example" }),
        "GET /api/settings/env?reveal=0": () => ({ text: "KEY=sk-…1234\n" }),
        "GET /api/settings/env?reveal=1": () => ({ text: "KEY=sk-secret-1234\n" }),
    });
    await els.settingsSampleBtn.click();
    assert.equal(els.settingsImportText.value, "OPENAI_API_KEY=sk-example");
    assert.equal(els.settingsImportPanel.hidden, false);
    await els.settingsEnvBtn.click();
    assert.equal(els.settingsImportPanel.hidden, true);
    assert.equal(els.settingsEnvText.value, "KEY=sk-…1234\n");
    await els.settingsEnvRevealBtn.click();
    assert.equal(els.settingsEnvText.value, "KEY=sk-secret-1234\n");
    els.settingsEnvCloseBtn.click();
    assert.equal(els.settingsEnvText.value, "");
    assert.equal(calls.at(-1).path, "/api/settings/env?reveal=1");
});

test("a server error is shown in the status line", async () => {
    const { els, feature } = harness({
        "PUT /api/settings": () => {
            throw new Error('{"error":"invalid setting name(s): x"}');
        },
    });
    await feature.load();
    const card = byTag(els.settingsBody, "details").find((n) => n.className === "settings-card");
    byTag(card, "input")[0].value = "k";
    await button(card, "Save").click();
    assert.equal(els.settingsStatus.textContent, "invalid setting name(s): x");
});

test("cog opens the modal and loads; X, backdrop click and tab buttons work", async () => {
    const { els, calls } = harness();
    await els.settingsOpenBtn.click();
    assert.equal(els.settingsDialog.open, true);
    assert.equal(calls.some((c) => c.path === "/api/settings"), true);

    els.settingsTabButtons[1].click();
    assert.equal(els.settingsPanels.providers.classes.has("active"), true);
    assert.equal(els.settingsPanels.global.classes.has("active"), false);
    assert.equal(els.settingsTabButtons[1].attrs["aria-selected"], "true");

    els.settingsDialog.listeners.click({ target: els.settingsBody }); // a click inside does nothing
    assert.equal(els.settingsDialog.open, true);
    els.settingsDialog.listeners.click({ target: els.settingsDialog }); // backdrop
    assert.equal(els.settingsDialog.open, false);

    await els.settingsOpenBtn.click();
    els.settingsCloseBtn.click();
    assert.equal(els.settingsDialog.open, false);
});

test("the first-run step opens on the import panel of the Providers tab with a hint", async () => {
    const { els, feature } = harness();
    await feature.openFirstRun();
    assert.equal(els.settingsDialog.open, true);
    assert.equal(els.settingsImportPanel.hidden, false);
    assert.equal(els.settingsPanels.providers.classes.has("active"), true);
    assert.match(els.settingsStatus.textContent, /Last setup step/);
    els.settingsCloseBtn.click(); // skip
    assert.equal(els.settingsDialog.open, false);
    assert.equal(els.settingsImportPanel.hidden, true);
});
