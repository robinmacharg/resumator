import test from "node:test";
import assert from "node:assert/strict";

import { createRoleWorkspaceFeature } from "../role-workspace-feature.js";

const localStorageKeys = {
    steering_text: "cvweb.steering_text",
    steering_enabled: "cvweb.steering_enabled",
    selected_theme: "cvweb.selected_theme",
    active_role_id: "cvweb.active_role_id",
    roles_local_copied: "cvweb.roles.local_copied",
};

function fakeElement(tag = "div") {
    const classes = new Set();
    return {
        tagName: tag,
        dataset: {},
        children: [],
        textContent: "",
        value: "",
        classList: {
            toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
            contains: (name) => classes.has(name),
        },
        attributes: {},
        listeners: {},
        setAttribute(name, value) {
            this.attributes[name] = value;
        },
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

function createLocalStorageMock(initial = {}) {
    const store = new Map(Object.entries(initial));
    return {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
    };
}

const ROLES = [
    { id: 1, name: "Quantum Base", company: "QB", status: "applied", lastRunAt: null, currentSteered: 1 },
    { id: 2, name: "Old", company: "", status: "closed", lastRunAt: null, currentSteered: 0 },
];

function roleRecord(id, extra = {}) {
    const base = ROLES.find((role) => role.id === id);
    return { ...base, jobspec: `job ${id}`, steeringText: "", steeringEnabled: 1, theme: null, ...extra };
}

function createHarness({ roles = ROLES, storage = {}, roleExtra = {}, confirm = () => true } = {}) {
    global.document = { createElement: fakeElement };
    global.localStorage = createLocalStorageMock(storage);
    const calls = {
        api: [],
        steering: [],
        theme: [],
        loadRuns: [],
        status: [],
        showRun: 0,
        reload: 0,
        onCreate: () => {},
    };
    const state = { activeRoleId: null, roles: [], cvSource: "role", diskFiles: {} };
    const editors = { cv: "", jobspec: "", prompt: "p", research_prompt: "rp", env: "" };
    const els = {
        body: fakeElement("body"),
        roleList: fakeElement("ul"),
        roleStatusSelect: fakeElement("select"),
        activeRoleLabel: fakeElement("strong"),
        cvSourceSelect: fakeElement("select"),
        fileLoadButtons: [
            Object.assign(fakeElement("button"), { dataset: { file: "cv" } }),
            Object.assign(fakeElement("button"), { dataset: { file: "prompt" } }),
        ],
    };
    const editableFiles = { cv: { tabLabel: "CV" } };
    const api = async (path, options = {}) => {
        const body = options.body ? JSON.parse(options.body) : null;
        calls.api.push({ path, method: options.method || "GET", body });
        if (path === "/api/roles" && !options.method) {
            return { roles };
        }
        if (path === "/api/roles") {
            calls.onCreate();
            return { role: roleRecord(1) };
        }
        const match = path.match(/^\/api\/roles\/(\d+)$/);
        if (match) {
            return { role: roleRecord(Number(match[1]), { ...roleExtra, ...(body || {}) }) };
        }
        if (path.endsWith("/cv")) {
            const content = body ? body.content : path.startsWith("/api/master") ? "master cv" : "role cv";
            return { cv: { content }, versions: [], unchanged: false };
        }
        return { success: true };
    };
    const feature = createRoleWorkspaceFeature({
        state,
        els,
        api,
        editableFiles,
        localStorageKeys,
        setStatus: (message, isError = false) => calls.status.push({ message, isError }),
        applyRoleFiles: (files) => {
            Object.entries(files).forEach(([key, value]) => {
                editors[key] = value;
                state.diskFiles[key] = value;
            });
        },
        syncDirtyIndicators: () => {},
        currentFileValues: () => ({ ...editors }),
        applySteering: (steering) => calls.steering.push(steering),
        applyTheme: (theme) => calls.theme.push(theme),
        roleRunsFeature: {
            loadRuns: async (roleId) => calls.loadRuns.push(roleId),
            showSelectedRun: () => {
                calls.showRun += 1;
            },
        },
        confirm,
        reloadPage: () => {
            calls.reload += 1;
        },
    });
    return { feature, state, els, editors, editableFiles, calls };
}

test("initialize with no roles stays in file mode", async () => {
    const { feature, state, els } = createHarness({ roles: [] });

    await feature.initialize();

    assert.equal(state.activeRoleId, null);
    assert.equal(feature.isActive(), false);
    assert.deepEqual(feature.getRoleOwnedKeys(), []);
    assert.equal(els.body.classList.contains("role-mode"), false);
    assert.equal(els.roleList.children[0].textContent, "No roles yet. Use + to add one.");
});

test("initialize opens the remembered role and fills the role-owned editors", async () => {
    const { feature, state, els, editors, editableFiles, calls } = createHarness({
        storage: { "cvweb.active_role_id": "2", "cvweb.roles.local_copied": "true" },
    });

    await feature.initialize();

    assert.equal(state.activeRoleId, 2);
    assert.deepEqual(feature.getRoleOwnedKeys(), ["cv", "jobspec"]);
    assert.equal(editors.cv, "role cv");
    assert.equal(editors.jobspec, "job 2");
    assert.deepEqual(calls.theme, ["default"]);
    assert.deepEqual(calls.loadRuns, [2]);
    assert.equal(els.body.classList.contains("role-mode"), true);
    assert.equal(editableFiles.cv.tabLabel, "Role CV");
    assert.equal(els.fileLoadButtons[0].textContent, "Reload");
    assert.equal(els.roleList.children.length, 2);
});

test("initialize falls back to the first open role", async () => {
    const { feature, state } = createHarness({ storage: { "cvweb.roles.local_copied": "true" } });

    await feature.initialize();

    assert.equal(state.activeRoleId, 1);
});

test("the first role opened gets this browser's steering and theme once", async () => {
    const { feature, calls } = createHarness({
        storage: {
            "cvweb.steering_text": "AI focus",
            "cvweb.steering_enabled": "false",
            "cvweb.selected_theme": "compact",
        },
    });

    await feature.initialize();

    const patch = calls.api.find((call) => call.method === "POST" && call.path === "/api/roles/1");
    assert.deepEqual(patch.body, { steeringText: "AI focus", steeringEnabled: false, theme: "compact" });
    assert.deepEqual(calls.steering, [{ text: "AI focus", enabled: false }]);
    assert.equal(localStorage.getItem("cvweb.roles.local_copied"), "true");
});

test("the one-time copy leaves a role's own steering and theme alone", async () => {
    const { feature, calls } = createHarness({
        storage: { "cvweb.steering_text": "AI focus", "cvweb.selected_theme": "compact" },
        roleExtra: { steeringText: "role note", theme: "default" },
    });

    await feature.initialize();

    assert.equal(calls.api.some((call) => call.method === "POST"), false);
});

test("switching role with unsaved edits asks first", async () => {
    let asked = 0;
    const { feature, state, editors } = createHarness({
        storage: { "cvweb.roles.local_copied": "true" },
        confirm: () => {
            asked += 1;
            return false;
        },
    });
    await feature.initialize();
    editors.cv = "edited";

    const switched = await feature.selectRole(2);

    assert.equal(switched, false);
    assert.equal(asked, 1);
    assert.equal(state.activeRoleId, 1);
});

test("saving the CV adds a role version; the master is saved when it is open", async () => {
    const { feature, state, els, editors, calls } = createHarness({
        storage: { "cvweb.roles.local_copied": "true" },
    });
    await feature.initialize();

    editors.cv = "new role cv";
    assert.equal(await feature.saveFile("cv"), true);
    assert.deepEqual(calls.api.at(-1), { path: "/api/roles/1/cv", method: "POST", body: { content: "new role cv" } });

    els.cvSourceSelect.value = "master";
    await feature.handleCvSourceChanged();
    assert.equal(state.cvSource, "master");
    assert.equal(editors.cv, "master cv");
    editors.cv = "new master";
    await feature.saveFile("cv");
    assert.equal(calls.api.at(-1).path, "/api/master/cv");

    assert.equal(await feature.saveFile("prompt"), false);
});

test("saving the job spec updates the role", async () => {
    const { feature, editors, calls } = createHarness({ storage: { "cvweb.roles.local_copied": "true" } });
    await feature.initialize();
    editors.jobspec = "new spec";

    await feature.saveFile("jobspec");

    assert.deepEqual(calls.api.at(-1), { path: "/api/roles/1", method: "POST", body: { jobspec: "new spec" } });
});

test("saveEditsBeforeRun saves dirty role editors and prompt files", async () => {
    const { feature, state, editors, calls } = createHarness({ storage: { "cvweb.roles.local_copied": "true" } });
    await feature.initialize();
    state.diskFiles.prompt = "p";
    state.diskFiles.research_prompt = "old";
    editors.jobspec = "changed";

    await feature.saveEditsBeforeRun();

    const posts = calls.api.filter((call) => call.method === "POST");
    assert.deepEqual(
        posts.map((call) => call.path),
        ["/api/roles/1", "/api/save"],
    );
    assert.deepEqual(posts[1].body, { files: { research_prompt: "rp" } });
});

test("steering and theme changes are saved on the role in role mode only", async () => {
    const { feature, calls } = createHarness({ storage: { "cvweb.roles.local_copied": "true" } });
    assert.equal(feature.handleSteeringChanged({ text: "x", enabled: true }), false);
    assert.equal(feature.handleThemeChanged("compact"), false);

    await feature.initialize();
    assert.equal(feature.handleSteeringChanged({ text: "focus", enabled: true }), true);
    await feature.flushSteering();
    assert.deepEqual(calls.api.at(-1).body, { steeringText: "focus", steeringEnabled: true });

    assert.equal(feature.handleThemeChanged("default"), true);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.api.at(-1).body, { theme: "" });
    assert.equal(calls.showRun, 1);
});

test("status changes archive the role; deleting the last role reloads the page", async () => {
    const roles = [ROLES[0]];
    const { feature, els, calls } = createHarness({ roles, storage: { "cvweb.roles.local_copied": "true" } });
    await feature.initialize();

    els.roleStatusSelect.value = "closed";
    await feature.handleStatusChanged();
    assert.deepEqual(calls.api.at(-1).body, { status: "closed" });

    roles.length = 0; // after the delete, /api/roles lists nothing
    await feature.deleteActiveRole();
    assert.equal(calls.api.some((call) => call.path === "/api/roles/1/delete"), true);
    assert.equal(calls.reload, 1);
});

test("createRoleFromDialog creates the role from the dialog and opens it", async () => {
    const roles = [];
    const { feature, state, els, calls } = createHarness({ roles });
    let closed = 0;
    Object.assign(els, {
        newRoleNameInput: { value: "  Quantum Base " },
        newRoleCompanyInput: { value: "QB" },
        newRoleJobspecInput: { value: "spec" },
        newRoleDialog: { close: () => (closed += 1) },
    });
    calls.onCreate = () => roles.push(ROLES[0]);

    await feature.createRoleFromDialog();

    const create = calls.api.find((call) => call.path === "/api/roles" && call.method === "POST");
    assert.deepEqual(create.body, { name: "Quantum Base", company: "QB", jobspec: "spec" });
    assert.equal(closed, 1);
    assert.equal(state.activeRoleId, 1);
});

test("createRoleFromDialog needs a name", async () => {
    const { feature, els, calls } = createHarness();
    Object.assign(els, { newRoleNameInput: { value: " " } });

    await feature.createRoleFromDialog();

    assert.equal(calls.api.length, 0);
    assert.deepEqual(calls.status.at(-1), { message: "A role needs a name.", isError: true });
});
