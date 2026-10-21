import { getStorageString, setStorageString } from "./storage-utils.js";

/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap (multi-role plan step 9).
 * - Responsibility: the role sidebar (list, create, status, delete), role selection, and the role-owned editors:
 *   the role or master CV and the job spec, saved through the Role API instead of `input/` files.
 *
 * Plain-language purpose:
 * - With roles in the DB the app is in "role mode": the CV and Job Spec tabs edit the selected role, steering and
 *   theme are kept on the role, and runs are stored per role. With no roles the app keeps today's file mode.
 */

const ROLE_OWNED_KEYS = ["cv", "jobspec"];
const PROMPT_FILE_KEYS = ["prompt", "research_prompt"];
const STATUSES = ["draft", "applied", "closed"];
const CV_LABELS = { role: "Role CV", master: "Master CV" };

/**
 * Dependencies required by the role workspace feature.
 *
 * @typedef {Object} RoleWorkspaceFeatureContext
 * @property {any} state Shared app state (activeRoleId, roles, cvSource, diskFiles).
 * @property {any} els DOM element registry (sidebar, dialog, editors, CV source picker).
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API helper.
 * @property {any} editableFiles Editable file metadata map (the CV tab label changes with the open CV).
 * @property {any} localStorageKeys Local storage key map.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 * @property {(files: {cv?: string, jobspec?: string}) => void} applyRoleFiles Set role-owned editors and snapshot.
 * @property {() => void} syncDirtyIndicators Update dirty markers.
 * @property {() => any} currentFileValues Editor values for every key, role-owned ones included.
 * @property {(steering: {text: string, enabled: boolean}) => void} applySteering Show a role's steering.
 * @property {(theme: string) => void} applyTheme Show a role's theme.
 * @property {any} roleRunsFeature Run-history API: loadRuns, clear.
 * @property {(message: string) => boolean} [confirm] Confirmation prompt (window.confirm).
 * @property {() => void} [reloadPage] Full page reload (after the last role is deleted).
 */

/**
 * Create the role workspace feature.
 *
 * @param {RoleWorkspaceFeatureContext} ctx Feature dependencies.
 */
export function createRoleWorkspaceFeature(ctx) {
    const {
        state,
        els,
        api,
        editableFiles,
        localStorageKeys,
        setStatus,
        applyRoleFiles,
        syncDirtyIndicators,
        currentFileValues,
        applySteering,
        applyTheme,
        roleRunsFeature,
    } = ctx;
    const confirmAction = ctx.confirm || ((message) => window.confirm(message));
    const reloadPage = ctx.reloadPage || (() => window.location.reload());

    let steeringTimer = null;
    let pendingSteering = null;

    /** @returns {boolean} */
    function isActive() {
        return state.activeRoleId !== null;
    }

    /** @returns {any | null} */
    function getActiveRole() {
        return state.roles.find((role) => role.id === state.activeRoleId) || null;
    }

    /** @returns {string[]} Editor keys the role owns while role mode is on. */
    function getRoleOwnedKeys() {
        return isActive() ? ROLE_OWNED_KEYS : [];
    }

    /**
     * Unsaved role-owned edits (the open CV or the job spec).
     * @returns {boolean}
     */
    function hasUnsavedEdits() {
        if (!isActive()) {
            return false;
        }
        const values = currentFileValues();
        return ROLE_OWNED_KEYS.some((key) => values[key] !== (state.diskFiles[key] || ""));
    }

    /**
     * Ask before dropping unsaved edits. True when there are none or the user agrees.
     * @param {string} action
     * @returns {boolean}
     */
    function confirmDiscard(action) {
        return !hasUnsavedEdits() || confirmAction(`Discard unsaved CV or job spec changes and ${action}?`);
    }

    /**
     * "21 Oct" style date for the sidebar.
     * @param {string | null | undefined} iso
     * @returns {string}
     */
    function shortDate(iso) {
        if (!iso) {
            return "";
        }
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    }

    /**
     * Body class, CV tab label, Load buttons and role controls for the current mode.
     * @returns {void}
     */
    function syncModeUi() {
        const active = isActive();
        if (els.body) {
            els.body.classList.toggle("role-mode", active);
        }
        editableFiles.cv.tabLabel = active ? CV_LABELS[state.cvSource] : "CV";
        if (els.cvSourceSelect) {
            els.cvSourceSelect.value = state.cvSource;
        }
        els.fileLoadButtons
            .filter((button) => ROLE_OWNED_KEYS.includes(button.dataset.file))
            .forEach((button) => {
                button.textContent = active ? "Reload" : "Load from Disk";
            });
        const role = getActiveRole();
        if (els.roleStatusSelect) {
            els.roleStatusSelect.value = role ? role.status : "draft";
        }
        if (els.activeRoleLabel) {
            els.activeRoleLabel.textContent = role
                ? `Role: ${role.name}${role.company ? ` (${role.company})` : ""}`
                : "";
        }
        syncDirtyIndicators();
    }

    /**
     * Render the role list. Closed roles are dimmed; the active one is marked.
     * @returns {void}
     */
    function renderSidebar() {
        if (!els.roleList) {
            return;
        }
        els.roleList.replaceChildren();
        if (!state.roles.length) {
            const empty = document.createElement("li");
            empty.className = "role-empty";
            empty.textContent = "No roles yet. Use + to add one.";
            els.roleList.appendChild(empty);
            return;
        }
        state.roles.forEach((role) => {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "role-item";
            button.dataset.roleId = String(role.id);
            button.classList.toggle("active", role.id === state.activeRoleId);
            button.classList.toggle("closed", role.status === "closed");
            button.setAttribute("aria-current", role.id === state.activeRoleId ? "true" : "false");

            const name = document.createElement("span");
            name.className = "role-name";
            name.textContent = `${role.currentSteered ? "🧭 " : ""}${role.name}`;
            const meta = document.createElement("span");
            meta.className = "role-meta";
            meta.textContent = [role.company, role.status, shortDate(role.lastRunAt)]
                .filter(Boolean)
                .join(" · ");
            button.append(name, meta);
            button.addEventListener("click", () => selectRole(role.id));
            item.appendChild(button);
            els.roleList.appendChild(item);
        });
    }

    /**
     * Reload the role list from the server.
     * @returns {Promise<void>}
     */
    async function refreshRoles() {
        const payload = await api("/api/roles");
        state.roles = payload.roles || [];
        renderSidebar();
    }

    /**
     * One-time copy of the browser's steering and theme (from before roles) into the first role opened.
     * @param {any} role
     * @returns {Promise<any>} The role, updated when anything was copied.
     */
    async function copyLocalSettingsOnce(role) {
        if (getStorageString(localStorageKeys.roles_local_copied) === "true") {
            return role;
        }
        setStorageString(localStorageKeys.roles_local_copied, "true");
        const patch = {};
        const text = (getStorageString(localStorageKeys.steering_text, "") || "").trim();
        if (text && !(role.steeringText || "").trim()) {
            patch.steeringText = text;
            patch.steeringEnabled = getStorageString(localStorageKeys.steering_enabled, "true") !== "false";
        }
        const theme = (getStorageString(localStorageKeys.selected_theme, "") || "").trim();
        if (theme && theme !== "default" && !role.theme) {
            patch.theme = theme;
        }
        if (!Object.keys(patch).length) {
            return role;
        }
        try {
            const result = await api(`/api/roles/${role.id}`, { method: "POST", body: JSON.stringify(patch) });
            return result.role || role;
        } catch (err) {
            setStatus(`Couldn't copy this browser's steering/theme to the role: ${err.message}`, true);
            return role;
        }
    }

    /**
     * Load the open CV (role or master) into the CV editor.
     * @returns {Promise<void>}
     */
    async function loadOpenCv() {
        const path = state.cvSource === "master" ? "/api/master/cv" : `/api/roles/${state.activeRoleId}/cv`;
        const payload = await api(path);
        applyRoleFiles({ cv: (payload.cv && payload.cv.content) || "" });
    }

    /**
     * Make a role active: its CV, job spec, steering, theme and runs fill the existing tabs.
     * @param {number} roleId
     * @param {{force?: boolean}} [options] force skips the unsaved-edits check (startup).
     * @returns {Promise<boolean>} False when cancelled or failed.
     */
    async function selectRole(roleId, options = {}) {
        if (!options.force && roleId === state.activeRoleId) {
            return true;
        }
        if (!options.force && !confirmDiscard("switch role")) {
            renderSidebar();
            return false;
        }
        await flushSteering();
        try {
            let { role } = await api(`/api/roles/${roleId}`);
            role = await copyLocalSettingsOnce(role);
            state.activeRoleId = role.id;
            state.cvSource = "role";
            state.roles = state.roles.map((item) => (item.id === role.id ? { ...item, ...role } : item));
            setStorageString(localStorageKeys.active_role_id, String(role.id));

            applyRoleFiles({ jobspec: role.jobspec || "" });
            await loadOpenCv();
            applySteering({ text: role.steeringText || "", enabled: Boolean(role.steeringEnabled) });
            applyTheme(role.theme || "default");
            syncModeUi();
            renderSidebar();
            await roleRunsFeature.loadRuns(role.id);
            setStatus(`Opened role "${role.name}".`);
            return true;
        } catch (err) {
            setStatus(`Couldn't open role: ${err.message}`, true);
            return false;
        }
    }

    /**
     * Startup: list roles and open the remembered one (or the first open role). No roles = file mode.
     * @returns {Promise<void>}
     */
    async function initialize() {
        try {
            await refreshRoles();
        } catch (err) {
            state.roles = [];
            renderSidebar();
            setStatus(`Role list unavailable, using input/ files: ${err.message}`, true);
            return;
        }
        if (!state.roles.length) {
            syncModeUi();
            return;
        }
        const savedId = Number(getStorageString(localStorageKeys.active_role_id, ""));
        const saved = state.roles.find((role) => role.id === savedId);
        const fallback = state.roles.find((role) => role.status !== "closed") || state.roles[0];
        await selectRole((saved || fallback).id, { force: true });
    }

    /**
     * Switch the CV editor between the role's CV and the master CV.
     * @returns {Promise<void>}
     */
    async function handleCvSourceChanged() {
        if (!els.cvSourceSelect || !isActive()) {
            return;
        }
        const next = els.cvSourceSelect.value === "master" ? "master" : "role";
        if (next === state.cvSource) {
            return;
        }
        const values = currentFileValues();
        if (values.cv !== (state.diskFiles.cv || "") && !confirmAction("Discard unsaved CV changes?")) {
            els.cvSourceSelect.value = state.cvSource;
            return;
        }
        state.cvSource = next;
        try {
            await loadOpenCv();
            syncModeUi();
            setStatus(next === "master" ? "Editing the master CV." : "Editing this role's CV.");
        } catch (err) {
            setStatus(`Couldn't load the ${CV_LABELS[next]}: ${err.message}`, true);
        }
    }

    /**
     * Save a role-owned editor through the Role API. Returns false for keys the role doesn't own.
     * @param {string} key Editable file key.
     * @returns {Promise<boolean>}
     */
    async function saveFile(key) {
        if (!getRoleOwnedKeys().includes(key)) {
            return false;
        }
        const value = currentFileValues()[key];
        const label = key === "cv" ? CV_LABELS[state.cvSource] : "Job spec";
        try {
            if (key === "cv") {
                const path = state.cvSource === "master" ? "/api/master/cv" : `/api/roles/${state.activeRoleId}/cv`;
                const result = await api(path, { method: "POST", body: JSON.stringify({ content: value }) });
                applyRoleFiles({ cv: (result.cv && result.cv.content) || value });
                setStatus(result.unchanged ? `${label} unchanged.` : `${label} saved as a new version.`);
            } else {
                await api(`/api/roles/${state.activeRoleId}`, {
                    method: "POST",
                    body: JSON.stringify({ jobspec: value }),
                });
                applyRoleFiles({ jobspec: value });
                setStatus(`${label} saved.`);
            }
        } catch (err) {
            setStatus(`Save failed: ${err.message}`, true);
            throw err;
        }
        return true;
    }

    /**
     * Reload a role-owned editor from the DB. Returns false for keys the role doesn't own.
     * @param {string} key
     * @returns {Promise<boolean>}
     */
    async function reloadFile(key) {
        if (!getRoleOwnedKeys().includes(key)) {
            return false;
        }
        try {
            if (key === "cv") {
                await loadOpenCv();
            } else {
                const { role } = await api(`/api/roles/${state.activeRoleId}`);
                applyRoleFiles({ jobspec: role.jobspec || "" });
            }
            setStatus("Reloaded.");
        } catch (err) {
            setStatus(`Reload failed: ${err.message}`, true);
        }
        return true;
    }

    /**
     * Save unsaved edits before a role run, so the run sees what the editors show: the role's CV and job spec,
     * steering, and the prompt files the runner still reads from `input/` (as file-mode runs do).
     * @returns {Promise<void>}
     */
    async function saveEditsBeforeRun() {
        await flushSteering();
        const values = currentFileValues();
        for (const key of ROLE_OWNED_KEYS) {
            if (values[key] !== (state.diskFiles[key] || "")) {
                await saveFile(key);
            }
        }
        const promptFiles = {};
        PROMPT_FILE_KEYS.forEach((key) => {
            if (values[key] !== (state.diskFiles[key] || "")) {
                promptFiles[key] = values[key];
            }
        });
        if (Object.keys(promptFiles).length) {
            await api("/api/save", { method: "POST", body: JSON.stringify({ files: promptFiles }) });
            Object.assign(state.diskFiles, promptFiles);
            syncDirtyIndicators();
        }
    }

    /**
     * Patch the active role and keep the sidebar copy in step.
     * @param {any} patch camelCase role fields.
     * @returns {Promise<any>}
     */
    async function updateActiveRole(patch) {
        const roleId = state.activeRoleId;
        const { role } = await api(`/api/roles/${roleId}`, { method: "POST", body: JSON.stringify(patch) });
        state.roles = state.roles.map((item) => (item.id === role.id ? { ...item, ...role } : item));
        return role;
    }

    /**
     * Send the pending steering change now (debounced edits, or before a run or role switch).
     * @returns {Promise<void>}
     */
    async function flushSteering() {
        if (steeringTimer) {
            clearTimeout(steeringTimer);
            steeringTimer = null;
        }
        if (!pendingSteering || !isActive()) {
            pendingSteering = null;
            return;
        }
        const steering = pendingSteering;
        pendingSteering = null;
        try {
            await updateActiveRole({ steeringText: steering.text, steeringEnabled: steering.enabled });
        } catch (err) {
            setStatus(`Couldn't save steering: ${err.message}`, true);
        }
    }

    /**
     * Steering edits in role mode go to the role (debounced). Returns false in file mode.
     * @param {{text: string, enabled: boolean}} steering
     * @returns {boolean} True when handled here.
     */
    function handleSteeringChanged(steering) {
        if (!isActive()) {
            return false;
        }
        pendingSteering = steering;
        if (steeringTimer) {
            clearTimeout(steeringTimer);
        }
        steeringTimer = setTimeout(() => {
            flushSteering();
        }, 600);
        return true;
    }

    /**
     * Theme changes in role mode are saved on the role and re-render the preview. Returns false in file mode.
     * @param {string} theme
     * @returns {boolean} True when handled here.
     */
    function handleThemeChanged(theme) {
        if (!isActive()) {
            return false;
        }
        updateActiveRole({ theme: theme === "default" ? "" : theme }).catch((err) => {
            setStatus(`Couldn't save the theme: ${err.message}`, true);
        });
        roleRunsFeature.showSelectedRun();
        return true;
    }

    /**
     * Status select: draft, applied or closed (archive, R21).
     * @returns {Promise<void>}
     */
    async function handleStatusChanged() {
        if (!els.roleStatusSelect || !isActive()) {
            return;
        }
        const status = els.roleStatusSelect.value;
        if (!STATUSES.includes(status)) {
            return;
        }
        try {
            await updateActiveRole({ status });
            renderSidebar();
            setStatus(status === "closed" ? "Role archived (closed)." : `Role marked ${status}.`);
        } catch (err) {
            setStatus(`Couldn't change the status: ${err.message}`, true);
            syncModeUi();
        }
    }

    /**
     * Delete the active role, its CV versions and runs, after confirmation.
     * @returns {Promise<void>}
     */
    async function deleteActiveRole() {
        const role = getActiveRole();
        if (!role) {
            return;
        }
        const ok = confirmAction(
            `Delete role "${role.name}" with its CV versions and runs? This can't be undone.`,
        );
        if (!ok) {
            return;
        }
        try {
            await api(`/api/roles/${role.id}/delete`, { method: "POST", body: JSON.stringify({}) });
            await refreshRoles();
            if (!state.roles.length) {
                reloadPage();
                return;
            }
            const next = state.roles.find((item) => item.status !== "closed") || state.roles[0];
            await selectRole(next.id, { force: true });
            setStatus(`Deleted role "${role.name}".`);
        } catch (err) {
            setStatus(`Delete failed: ${err.message}`, true);
        }
    }

    /**
     * Open the new-role dialog.
     * @returns {void}
     */
    function openNewRoleDialog() {
        if (!els.newRoleDialog) {
            return;
        }
        els.newRoleNameInput.value = "";
        els.newRoleCompanyInput.value = "";
        els.newRoleJobspecInput.value = "";
        els.newRoleDialog.showModal();
        els.newRoleNameInput.focus();
    }

    /**
     * Create a role from the dialog (its CV is seeded from the master) and open it.
     * @returns {Promise<void>}
     */
    async function createRoleFromDialog() {
        const name = (els.newRoleNameInput.value || "").trim();
        if (!name) {
            setStatus("A role needs a name.", true);
            return;
        }
        try {
            const { role } = await api("/api/roles", {
                method: "POST",
                body: JSON.stringify({
                    name,
                    company: (els.newRoleCompanyInput.value || "").trim(),
                    jobspec: els.newRoleJobspecInput.value || "",
                }),
            });
            els.newRoleDialog.close();
            await refreshRoles();
            const wasFileMode = !isActive();
            await selectRole(role.id, { force: wasFileMode });
            setStatus(`Created role "${role.name}" with a copy of the master CV.`);
        } catch (err) {
            setStatus(`Couldn't create the role: ${err.message}`, true);
        }
    }

    return {
        isActive,
        getActiveRole,
        getRoleOwnedKeys,
        hasUnsavedEdits,
        initialize,
        refreshRoles,
        renderSidebar,
        selectRole,
        handleCvSourceChanged,
        saveFile,
        reloadFile,
        saveEditsBeforeRun,
        flushSteering,
        handleSteeringChanged,
        handleThemeChanged,
        handleStatusChanged,
        deleteActiveRole,
        openNewRoleDialog,
        createRoleFromDialog,
    };
}
