/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap (multi-role plan steps 10 and 11).
 * - Responsibility: "Promote to master", "Pull from master" (`GET/POST /api/roles/<id>/merge`) and "Import
 *   input/CV.md as master" (`GET/POST /api/master/import`): the merge view dialog, then reloading the open CV.
 *
 * Plain-language purpose:
 * - Shows each changed CV entry with a checkbox and an inline diff. Removals start unticked so nothing is lost by
 *   accident; conflicts (changed on both sides) must be resolved by keeping one side or editing the text.
 */

const DIRECTION_TEXT = {
    promote: {
        title: "Promote to master",
        hint: "Changes in this role's CV since it last synced with the master. Ticked ones are copied into the master.",
        current: "master",
        incoming: "role CV",
        none: "Nothing to promote: the master already has this role's changes.",
        done: "Promoted to the master CV.",
    },
    pull: {
        title: "Pull from master",
        hint: "Master changes since this role last synced. Ticked ones are copied into the role's CV; its own edits stay.",
        current: "role CV",
        incoming: "master",
        none: "Nothing to pull: the role CV is up to date with the master.",
        done: "Pulled master changes into the role CV.",
    },
    import: {
        title: "Import input/CV.md as master",
        hint: "Changes in input/CV.md since it was last imported. Ticked ones are copied into the master.",
        current: "master",
        incoming: "file",
        none: "Nothing to import: input/CV.md has no changes since it was last imported.",
        done: "Imported input/CV.md into the master CV.",
    },
};

const STATUS_TEXT = {
    added: "added",
    removed: "removed",
    changed: "changed",
    conflict: "conflict",
};

/** Bootstrap badge colour per change status. */
const STATUS_BADGE = {
    added: "text-bg-success",
    removed: "text-bg-secondary",
    changed: "text-bg-secondary",
    conflict: "text-bg-danger",
};

/**
 * Dependencies required by the role merge feature.
 *
 * @typedef {Object} RoleMergeFeatureContext
 * @property {any} state Shared app state (activeRoleId, diskFiles).
 * @property {any} els DOM element registry (merge dialog, list, buttons).
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API helper.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 * @property {() => any} currentFileValues Editor values for every key.
 * @property {() => Promise<void>} loadOpenCv Reload the open CV (role or master) into the editor.
 */

/**
 * Create the role merge feature.
 *
 * @param {RoleMergeFeatureContext} ctx Feature dependencies.
 */
export function createRoleMergeFeature(ctx) {
    const { state, els, api, setStatus, currentFileValues, loadOpenCv } = ctx;

    /** @type {{direction: string, view: any, controls: any[]} | null} */
    let open = null;

    /**
     * Unit title as written in the CV: `## Entry`, `# Section` or the preamble.
     * @param {any} change
     * @returns {string}
     */
    function unitTitle(change) {
        if (change.kind === "preamble") {
            return "Preamble (before the first section)";
        }
        const marker = change.kind === "section" ? "#" : "##";
        const section = change.kind === "entry" && change.key[0] ? ` (in ${change.key[0]})` : "";
        return `${marker} ${change.heading}${section}`;
    }

    /**
     * Inline diff: one line per element, coloured by its +/- prefix.
     * @param {string} diff Unified diff without file headers.
     * @returns {HTMLElement}
     */
    function renderDiff(diff) {
        const pre = document.createElement("pre");
        pre.className = "merge-diff";
        (diff || "").split("\n").forEach((line) => {
            const span = document.createElement("span");
            if (line.startsWith("+")) {
                span.className = "diff-add";
            } else if (line.startsWith("-")) {
                span.className = "diff-del";
            } else if (line.startsWith("@@")) {
                span.className = "diff-hunk";
            }
            span.textContent = `${line}\n`;
            pre.appendChild(span);
        });
        return pre;
    }

    /**
     * Keep / take / edit choices for a conflict. Nothing is chosen at first, so the user must decide.
     * @param {any} change
     * @param {number} index
     * @param {any} text Direction labels.
     * @returns {{element: HTMLElement, radios: any[], textarea: any}}
     */
    function renderConflictChoices(change, index, text) {
        const group = document.createElement("div");
        group.className = "merge-choices";
        const textarea = document.createElement("textarea");
        textarea.className = "merge-edit";
        textarea.spellcheck = false;
        textarea.value = change.current || "";
        textarea.hidden = true;
        const options = [
            ["current", `Keep the ${text.current}'s version`],
            ["incoming", `Take the ${text.incoming}'s version`],
            ["edit", "Edit (blank removes the entry)"],
        ];
        const radios = options.map(([value, label]) => {
            const wrapper = document.createElement("label");
            const radio = document.createElement("input");
            radio.type = "radio";
            radio.className = "form-check-input";
            radio.name = `merge-conflict-${index}`;
            radio.value = value;
            radio.addEventListener("change", () => {
                textarea.hidden = value !== "edit";
            });
            const caption = document.createElement("span");
            caption.textContent = label;
            wrapper.append(radio, caption);
            group.appendChild(wrapper);
            return radio;
        });
        group.appendChild(textarea);
        return { element: group, radios, textarea };
    }

    /**
     * Render the open view's changes into the dialog list.
     * @returns {void}
     */
    function renderView() {
        const text = DIRECTION_TEXT[open.direction];
        els.mergeTitle.textContent = text.title;
        els.mergeHint.textContent = text.hint;
        els.mergeError.textContent = "";
        els.mergeList.replaceChildren();
        open.controls = open.view.changes.map((change, index) => {
            const item = document.createElement("li");
            item.className = `merge-item merge-${change.status}`;
            const head = document.createElement("label");
            head.className = "merge-item-head";
            const control = { change, checkbox: null, radios: null, textarea: null };
            if (change.status !== "conflict") {
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "form-check-input";
                checkbox.checked = Boolean(change.accept);
                head.appendChild(checkbox);
                control.checkbox = checkbox;
            }
            const title = document.createElement("span");
            title.className = "merge-item-title";
            title.textContent = unitTitle(change);
            const badge = document.createElement("span");
            badge.className = `merge-badge badge ${STATUS_BADGE[change.status] || "text-bg-secondary"}`;
            badge.textContent = STATUS_TEXT[change.status] || change.status;
            head.append(title, badge);
            item.append(head, renderDiff(change.diff));
            if (change.status === "conflict") {
                const choices = renderConflictChoices(change, index, text);
                item.appendChild(choices.element);
                control.radios = choices.radios;
                control.textarea = choices.textarea;
            }
            els.mergeList.appendChild(item);
            return control;
        });
    }

    /**
     * Open the merge view for a direction. Refuses while the CV editor has unsaved edits.
     * @param {"promote" | "pull" | "import"} direction
     * @returns {Promise<void>}
     */
    async function openMerge(direction) {
        if (state.activeRoleId === null) {
            return;
        }
        const text = DIRECTION_TEXT[direction];
        if ((currentFileValues().cv || "") !== (state.diskFiles.cv || "")) {
            setStatus(`Save or reload the CV before "${text.title}".`, true);
            return;
        }
        try {
            const path =
                direction === "import"
                    ? "/api/master/import"
                    : `/api/roles/${state.activeRoleId}/merge?direction=${direction}`;
            const view = await api(path);
            if (!view.changes.length) {
                if (direction === "pull" && view.baseBehind) {
                    // Nothing to merge, but record that the role is now in sync with the newer master.
                    await saveDecisions(direction, view, [], []);
                }
                setStatus(text.none);
                return;
            }
            open = { direction, view, controls: [] };
            renderView();
            els.mergeDialog.showModal();
        } catch (err) {
            setStatus(`Couldn't open "${text.title}": ${err.message}`, true);
        }
    }

    /**
     * POST the decisions for a view.
     * @returns {Promise<any>}
     */
    function saveDecisions(direction, view, accept, resolutions) {
        if (direction === "import") {
            return api("/api/master/import", {
                method: "POST",
                body: JSON.stringify({ targetId: view.targetId, sourceHash: view.sourceHash, accept, resolutions }),
            });
        }
        return api(`/api/roles/${state.activeRoleId}/merge`, {
            method: "POST",
            body: JSON.stringify({
                direction,
                targetId: view.targetId,
                sourceId: view.sourceId,
                accept,
                resolutions,
            }),
        });
    }

    /**
     * Collect the ticks and conflict choices, save, then reload the open CV.
     * @returns {Promise<void>}
     */
    async function applyMerge() {
        if (!open) {
            return;
        }
        const accept = [];
        const resolutions = [];
        let unresolved = 0;
        open.controls.forEach(({ change, checkbox, radios, textarea }) => {
            if (checkbox) {
                if (checkbox.checked) {
                    accept.push(change.key);
                }
                return;
            }
            const chosen = radios.find((radio) => radio.checked);
            if (!chosen) {
                unresolved += 1;
                return;
            }
            const resolution = { key: change.key, choice: chosen.value };
            if (chosen.value === "edit") {
                resolution.text = textarea.value;
            }
            resolutions.push(resolution);
        });
        if (unresolved) {
            els.mergeError.textContent = `Choose a version for every conflict (${unresolved} left).`;
            return;
        }
        const { direction, view } = open;
        const text = DIRECTION_TEXT[direction];
        try {
            const result = await saveDecisions(direction, view, accept, resolutions);
            closeMerge();
            await loadOpenCv();
            setStatus(result.unchanged ? `${text.title}: nothing was applied.` : text.done);
        } catch (err) {
            els.mergeError.textContent = err.message;
        }
    }

    /**
     * Close the dialog without saving.
     * @returns {void}
     */
    function closeMerge() {
        open = null;
        if (els.mergeDialog && els.mergeDialog.open) {
            els.mergeDialog.close();
        }
    }

    return {
        openMerge,
        applyMerge,
        closeMerge,
    };
}
