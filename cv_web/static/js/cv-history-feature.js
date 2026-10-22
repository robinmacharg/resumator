/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap (multi-role plan step 11).
 * - Responsibility: the version history of the open CV (role or master): list versions, view one, and restore it
 *   as a new version (`…/cv/versions/<id>` and `…/restore` on the Role API).
 *
 * Plain-language purpose:
 * - Every save, promote, pull and import adds a CV version (R8). This dialog lets the user look back and bring an
 *   old version back without losing anything: a restore is itself a new version.
 */

const SOURCE_TEXT = {
    seed: "copied from master",
    edit: "edited",
    promote: "promoted",
    pull: "pulled from master",
    import: "imported",
    example: "example",
};

/**
 * Dependencies required by the CV history feature.
 *
 * @typedef {Object} CvHistoryFeatureContext
 * @property {any} state Shared app state (activeRoleId, cvSource, diskFiles).
 * @property {any} els DOM element registry (history dialog, list, content, buttons).
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API helper.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 * @property {() => any} currentFileValues Editor values for every key.
 * @property {() => Promise<void>} loadOpenCv Reload the open CV (role or master) into the editor.
 * @property {(value: string) => string} formatDateTime Date/time formatter.
 */

/**
 * Create the CV history feature.
 *
 * @param {CvHistoryFeatureContext} ctx Feature dependencies.
 */
export function createCvHistoryFeature(ctx) {
    const { state, els, api, setStatus, currentFileValues, loadOpenCv, formatDateTime } = ctx;

    /** @type {{base: string, currentId: number | null, selectedId: number | null} | null} */
    let open = null;

    /** @returns {string} API path of the open CV. */
    function cvPath() {
        return state.cvSource === "master" ? "/api/master/cv" : `/api/roles/${state.activeRoleId}/cv`;
    }

    /**
     * One list line: "v12 · 21 Oct 14:03 · edited · note".
     * @param {any} version
     * @param {boolean} isCurrent
     * @returns {string}
     */
    function versionLabel(version, isCurrent) {
        return [
            `v${version.id}${isCurrent ? " (current)" : ""}`,
            formatDateTime(version.createdAt),
            SOURCE_TEXT[version.source] || version.source,
            version.note || "",
        ]
            .filter(Boolean)
            .join(" · ");
    }

    /**
     * Open the history dialog for the open CV.
     * @returns {Promise<void>}
     */
    async function openHistory() {
        if (state.activeRoleId === null) {
            return;
        }
        try {
            const payload = await api(cvPath());
            const versions = payload.versions || [];
            open = { base: cvPath(), currentId: versions.length ? versions[0].id : null, selectedId: null };
            els.historyTitle.textContent = state.cvSource === "master" ? "Master CV history" : "Role CV history";
            els.historyError.textContent = "";
            els.historyContent.textContent = "Pick a version to see it.";
            els.historyRestoreBtn.disabled = true;
            els.historyList.replaceChildren();
            versions.forEach((version) => {
                const item = document.createElement("li");
                const button = document.createElement("button");
                button.type = "button";
                button.className = "history-item list-group-item list-group-item-action";
                button.dataset.versionId = String(version.id);
                button.textContent = versionLabel(version, version.id === open.currentId);
                button.addEventListener("click", () => showVersion(version.id));
                item.appendChild(button);
                els.historyList.appendChild(item);
            });
            els.historyDialog.showModal();
        } catch (err) {
            setStatus(`Couldn't load the CV history: ${err.message}`, true);
        }
    }

    /**
     * Show one version's text; the current one can't be restored.
     * @param {number} versionId
     * @returns {Promise<void>}
     */
    async function showVersion(versionId) {
        if (!open) {
            return;
        }
        try {
            const { version } = await api(`${open.base}/versions/${versionId}`);
            open.selectedId = versionId;
            els.historyContent.textContent = version.content;
            els.historyRestoreBtn.disabled = versionId === open.currentId;
            els.historyError.textContent = "";
            Array.from(els.historyList.children).forEach((item) => {
                const button = item.children[0];
                button.classList.toggle("active", button.dataset.versionId === String(versionId));
            });
        } catch (err) {
            els.historyError.textContent = err.message;
        }
    }

    /**
     * Restore the selected version as a new version, then reload the open CV.
     * @returns {Promise<void>}
     */
    async function restoreSelected() {
        if (!open || open.selectedId === null) {
            return;
        }
        if ((currentFileValues().cv || "") !== (state.diskFiles.cv || "")) {
            els.historyError.textContent = "Save or reload the CV before restoring a version.";
            return;
        }
        const versionId = open.selectedId;
        try {
            const result = await api(`${open.base}/versions/${versionId}/restore`, {
                method: "POST",
                body: JSON.stringify({}),
            });
            closeHistory();
            await loadOpenCv();
            setStatus(
                result.unchanged
                    ? `Version ${versionId} is the same as the current CV.`
                    : `Restored version ${versionId} as a new version.`,
            );
        } catch (err) {
            els.historyError.textContent = err.message;
        }
    }

    /**
     * Close the dialog.
     * @returns {void}
     */
    function closeHistory() {
        open = null;
        if (els.historyDialog && els.historyDialog.open) {
            els.historyDialog.close();
        }
    }

    return {
        openHistory,
        showVersion,
        restoreSelected,
        closeHistory,
    };
}
