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

function createHarness({
    roles = ROLES,
    storage = {},
    roleExtra = {},
    confirm = () => true,
    setup = { needed: false },
    setupRoles = ROLES,
} = {}) {
    global.document = { createElement: fakeElement };
    global.localStorage = createLocalStorageMock(storage);
    const calls = {
        api: [],
        steering: [],
        theme: [],
        loadRuns: [],
        research: [],
        status: [],
        showRun: 0,
        reload: 0,
        dialog: [],
        tailored: 0,
        firstRunPreview: 0,
        settingsStep: 0,
        onCreate: () => {},
    };
    const state = { workspace: false, activeRoleId: null, roles: [], cvSource: "role", diskFiles: {} };
    const editors = { cv: "", jobspec: "", prompt: "p", research_prompt: "rp" };
    const els = {
        body: fakeElement("body"),
        roleList: fakeElement("ul"),
        roleStatusSelect: fakeElement("select"),
        activeRoleLabel: fakeElement("strong"),
        roleTitleBtn: fakeElement("button"),
        roleNameInput: Object.assign(fakeElement("input"), {
            hidden: true,
            focus() {},
            select() {},
            blur() {},
        }),
        cvSourceSelect: fakeElement("select"),
        jobspecEditor: fakeElement("textarea"),
        firstRunDialog: {
            showModal: () => calls.dialog.push("open"),
            close: () => calls.dialog.push("close"),
        },
        firstRunError: fakeElement("p"),
        fileLoadButtons: [
            Object.assign(fakeElement("button"), { dataset: { file: "cv" } }),
            Object.assign(fakeElement("button"), { dataset: { file: "prompt" } }),
        ],
    };
    const editableFiles = { cv: { tabLabel: "CV" } };
    const api = async (path, options = {}) => {
        const body = options.body ? JSON.parse(options.body) : null;
        calls.api.push({ path, method: options.method || "GET", body });
        if (path === "/api/setup") {
            if (!options.method) {
                return setup;
            }
            if (body.choice === "fail") {
                throw new Error("First-run setup is already done");
            }
            roles = body.choice === "example" ? setupRoles : [];
            return { success: true, choice: body.choice };
        }
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
        openSettingsStep: () => {
            calls.settingsStep += 1;
        },
        roleRunsFeature: {
            loadRuns: async (roleId) => calls.loadRuns.push(roleId),
            showSelectedRun: () => {
                calls.showRun += 1;
            },
            refreshTailoredOutput: async () => {
                calls.tailored += 1;
            },
            showFirstRun: () => {
                calls.firstRunPreview += 1;
            },
        },
        loadRoleResearch: async (roleId) => calls.research.push(roleId),
        confirm,
        reloadPage: () => {
            calls.reload += 1;
        },
    });
    return { feature, state, els, editors, editableFiles, calls };
}

test("initialize on a new install offers the first-run choice and stays out of role mode", async () => {
    const { feature, state, els, calls, editors } = createHarness({ roles: [], setup: { needed: true } });
    editors.cv = "cv from input/";
    editors.jobspec = "job from input/";

    await feature.initialize();

    assert.deepEqual(calls.dialog, ["open"]);
    assert.deepEqual([editors.cv, editors.jobspec], ["", ""]);
    assert.equal(calls.firstRunPreview, 1);
    assert.deepEqual(calls.research, [null]);
    assert.equal(state.workspace, false);
    assert.deepEqual(feature.getRoleOwnedKeys(), []);
    assert.equal(els.body.classList.contains("role-mode"), false);
    assert.equal(els.roleList.children[0].textContent, "No roles yet. Use + to add one.");
});

test("initialize falls back to file mode when the role API is unavailable", async () => {
    const { feature, state, els, calls } = createHarness();
    global.document = { createElement: fakeElement };
    const failing = createRoleWorkspaceFeature({
        state,
        els,
        api: async () => {
            throw new Error("down");
        },
        editableFiles: { cv: { tabLabel: "CV" } },
        localStorageKeys,
        setStatus: (message, isError) => calls.status.push({ message, isError }),
        syncDirtyIndicators: () => {},
    });

    await failing.initialize();

    assert.equal(state.workspace, false);
    assert.deepEqual(failing.getRoleOwnedKeys(), []);
    assert.match(calls.status.at(-1).message, /using input\/ files: down/);
});

test("with no roles but a master, only the master CV is open", async () => {
    const { feature, state, els, editors, editableFiles, calls } = createHarness({ roles: [] });

    await feature.initialize();

    assert.equal(state.workspace, true);
    assert.equal(feature.isMasterOnly(), true);
    assert.equal(state.cvSource, "master");
    assert.deepEqual(feature.getRoleOwnedKeys(), ["cv", "jobspec"]);
    assert.equal(editors.cv, "master cv");
    assert.equal(editors.jobspec, "");
    assert.equal(els.body.classList.contains("role-mode"), true);
    assert.equal(els.body.classList.contains("no-role"), true);
    assert.equal(els.body.classList.contains("cv-master"), true);
    assert.equal(els.jobspecEditor.readOnly, true);
    assert.equal(editableFiles.cv.tabLabel, "Master CV");
    assert.deepEqual([calls.showRun, calls.tailored], [1, 1]);
    assert.deepEqual(calls.research, [null]);
});

test("with no role the master saves, the job spec and theme changes are held back", async () => {
    const { feature, editors, calls } = createHarness({ roles: [] });
    await feature.initialize();

    editors.cv = "edited master";
    await feature.saveFile("cv");
    editors.jobspec = "spec";
    assert.equal(await feature.saveFile("jobspec"), true);
    assert.equal(feature.handleThemeChanged("compact"), true);
    assert.equal(feature.handleSteeringChanged({ text: "x", enabled: true }), false);

    const posts = calls.api.filter((call) => call.method === "POST");
    assert.deepEqual(posts.map((call) => call.path), ["/api/master/cv"]);
    assert.equal(calls.status.at(-1).isError, true);
    assert.equal(calls.showRun, 1);
});

test("choosing example data loads the example role", async () => {
    const { feature, state, els, calls } = createHarness({
        roles: [],
        setup: { needed: true },
        storage: { "cvweb.roles.local_copied": "true" },
    });
    await feature.initialize();

    assert.equal(await feature.chooseFirstRun("example"), true);

    assert.deepEqual(calls.dialog, ["open", "close"]);
    feature.handleFirstRunDialogClosed();
    assert.deepEqual(calls.dialog, ["open", "close"]);
    assert.deepEqual(calls.api.find((call) => call.method === "POST").body, { choice: "example" });
    assert.equal(state.workspace, true);
    assert.equal(state.activeRoleId, 1);
    assert.equal(els.body.classList.contains("no-role"), false);
    assert.match(calls.status.at(-1).message, /Example data loaded/);
    assert.equal(calls.settingsStep, 1);
});

test("choosing blank opens the master alone; a refusal keeps the dialog open", async () => {
    const { feature, state, els, calls } = createHarness({ roles: [], setup: { needed: true } });
    await feature.initialize();

    feature.handleFirstRunDialogClosed();
    assert.deepEqual(calls.dialog, ["open", "open"]);
    calls.dialog.length = 1;
    assert.equal(await feature.chooseFirstRun("fail"), false);
    assert.deepEqual(calls.dialog, ["open"]);
    assert.equal(els.firstRunError.textContent, "First-run setup is already done");

    assert.equal(calls.settingsStep, 0);

    assert.equal(await feature.chooseFirstRun("blank"), true);
    assert.equal(state.workspace, true);
    assert.equal(state.activeRoleId, null);
    assert.equal(state.cvSource, "master");
    assert.equal(calls.settingsStep, 1);
});

test("the Settings step is skipped when settings are already stored", async () => {
    const { feature, calls } = createHarness({ roles: [], setup: { needed: true, hasSettings: true } });
    await feature.initialize();
    assert.equal(await feature.chooseFirstRun("blank"), true);
    assert.equal(calls.settingsStep, 0);
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
    assert.deepEqual(calls.research, [2]);
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

test("renaming the role saves a changed name on blur and skips unchanged or blank names", async () => {
    const { feature, els, calls } = createHarness({ storage: { "cvweb.roles.local_copied": "true" } });
    await feature.initialize();
    const role = feature.getActiveRole();
    const before = calls.api.length;

    feature.startRename();
    assert.equal(els.roleNameInput.hidden, false);
    assert.equal(els.roleTitleBtn.hidden, true);
    assert.equal(els.roleNameInput.value, role.name);
    await feature.commitRename();
    assert.equal(els.roleNameInput.hidden, true);
    assert.equal(els.roleTitleBtn.hidden, false);

    feature.startRename();
    els.roleNameInput.value = "   ";
    await feature.commitRename();
    assert.equal(calls.api.length, before);

    feature.startRename();
    els.roleNameInput.value = "Discarded";
    feature.handleRenameKeydown({ key: "Escape", preventDefault() {} });
    await feature.commitRename();
    assert.equal(calls.api.length, before);

    feature.startRename();
    els.roleNameInput.value = "  Staff Engineer ";
    await feature.commitRename();
    assert.deepEqual(calls.api.at(-1), {
        path: `/api/roles/${role.id}`,
        method: "POST",
        body: { name: "Staff Engineer" },
    });
    assert.match(els.activeRoleLabel.textContent, /Staff Engineer/);
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
