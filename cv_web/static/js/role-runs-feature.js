/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap (multi-role plan step 9).
 * - Responsibility: the active role's CV run history: the run picker, the PDF preview source for the picked run
 *   (rendered on demand by the server, R16), and the Tailored tab text for that run.
 *
 * Plain-language purpose:
 * - Every CV run of a role is kept. The picker chooses which run's PDF to look at, in the role's current theme.
 */

/**
 * Dependencies required by the role runs feature.
 *
 * @typedef {Object} RoleRunsFeatureContext
 * @property {any} state Shared app state (activeRoleId, cvRuns, selectedCvRunId, selectedTheme).
 * @property {any} els DOM element registry (runSelect, tailoredViewer, tailoredTitle).
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API helper.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 * @property {(source: any) => void} setCvRunSource Preview source for role runs (null = file mode).
 * @property {() => void} updatePreview Re-render the preview.
 * @property {(iso: string) => string} formatDateTime Short date-time formatter.
 */

/**
 * Create the role runs feature.
 *
 * @param {RoleRunsFeatureContext} ctx Feature dependencies.
 */
export function createRoleRunsFeature(ctx) {
    const { state, els, api, setStatus, setCvRunSource, updatePreview, formatDateTime } = ctx;

    /** @returns {any | null} */
    function selectedRun() {
        return state.cvRuns.find((run) => run.id === state.selectedCvRunId) || null;
    }

    /**
     * Picker label: "#3 · 21 Oct 14:02 · claude/sonnet · 🧭 · current".
     * @param {any} run
     * @returns {string}
     */
    function runLabel(run) {
        const model = [run.provider, run.model].filter(Boolean).join("/");
        return [
            `#${run.id}`,
            formatDateTime(run.finishedAt || run.startedAt),
            model,
            (run.steeringText || "").trim() ? "🧭" : "",
            run.isCurrent ? "current" : "",
            run.success ? "" : "failed",
        ]
            .filter(Boolean)
            .join(" · ");
    }

    /**
     * Fill the run picker from state.cvRuns.
     * @returns {void}
     */
    function renderRunSelect() {
        if (!els.runSelect) {
            return;
        }
        els.runSelect.replaceChildren();
        if (!state.cvRuns.length) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No runs yet";
            els.runSelect.appendChild(opt);
            return;
        }
        state.cvRuns.forEach((run) => {
            const opt = document.createElement("option");
            opt.value = String(run.id);
            opt.textContent = runLabel(run);
            opt.disabled = !run.success;
            els.runSelect.appendChild(opt);
        });
        els.runSelect.value = state.selectedCvRunId === null ? "" : String(state.selectedCvRunId);
    }

    /**
     * Point the preview at the picked run in the selected theme ("default" = the default theme).
     * @returns {void}
     */
    function showSelectedRun() {
        const noRole = state.activeRoleId === null;
        if (noRole && !state.workspace) {
            return;
        }
        const run = noRole ? null : selectedRun();
        if (!run) {
            const source = { url: null, docxUrl: null, label: "no runs yet", steering: "", generatedAt: null };
            setCvRunSource(noRole ? { ...source, label: "no role yet", placeholder: "No role yet: add one with +" } : source);
            updatePreview();
            return;
        }
        const theme = state.selectedTheme && state.selectedTheme !== "default" ? state.selectedTheme : "";
        const base = `/api/roles/${state.activeRoleId}/runs/cv/${run.id}`;
        setCvRunSource({
            url: `${base}/cv.pdf?theme=${encodeURIComponent(theme)}`,
            docxUrl: `${base}/cv.docx`,
            label: `run #${run.id}`,
            steering: (run.steeringText || "").trim(),
            generatedAt: run.finishedAt || run.startedAt,
        });
        updatePreview();
    }

    /**
     * Load the role's CV runs and pick one: the given run, else the current run, else the newest success.
     * @param {number} roleId
     * @param {{selectRunId?: number | null}} [options]
     * @returns {Promise<void>}
     */
    async function loadRuns(roleId, options = {}) {
        const payload = await api(`/api/roles/${roleId}/runs`);
        state.cvRuns = payload.cvRuns || [];
        const wanted = state.cvRuns.find((run) => run.id === options.selectRunId && run.success);
        const current = state.cvRuns.find((run) => run.isCurrent);
        const newest = state.cvRuns.find((run) => run.success);
        state.selectedCvRunId = (wanted || current || newest || { id: null }).id;
        renderRunSelect();
        showSelectedRun();
        await refreshTailoredOutput();
    }

    /**
     * Picker change: preview that run.
     * @returns {Promise<void>}
     */
    async function handleRunSelectChanged() {
        if (!els.runSelect) {
            return;
        }
        const id = Number(els.runSelect.value);
        state.selectedCvRunId = Number.isFinite(id) && id > 0 ? id : null;
        showSelectedRun();
        await refreshTailoredOutput();
    }

    /**
     * Tailored tab in role mode: the picked run's model JSON (tagged markdown isn't stored, R6).
     * @returns {Promise<boolean>} False in file mode, so the caller shows output/tailored.md.
     */
    async function refreshTailoredOutput() {
        const noRole = state.activeRoleId === null;
        if (noRole && !state.workspace) {
            return false;
        }
        if (!els.tailoredViewer) {
            return true;
        }
        if (noRole) {
            if (els.tailoredTitle) {
                els.tailoredTitle.textContent = "Model output";
            }
            els.tailoredViewer.value = "No role yet. Add one with + to tailor the master CV.";
            return true;
        }
        const run = selectedRun();
        if (els.tailoredTitle) {
            els.tailoredTitle.textContent = run ? `Run #${run.id} model output (read-only)` : "Model output";
        }
        if (!run) {
            els.tailoredViewer.value = "No runs yet for this role. Run the full pipeline first.";
            return true;
        }
        try {
            const { run: full } = await api(`/api/roles/${state.activeRoleId}/runs/cv/${run.id}`);
            let text = full.rawOutput || "";
            if (full.modelJson) {
                text = JSON.stringify(full.modelJson, null, 2);
            }
            els.tailoredViewer.value = text || "This run has no output.";
        } catch (err) {
            els.tailoredViewer.value = `Couldn't load run #${run.id}: ${err.message}`;
        }
        return true;
    }

    /**
     * After a role CV run: reload the history and show the new run when it succeeded.
     * @param {number} roleId Role the run was started for.
     * @param {any} run Final run status (`runId` once saved).
     * @returns {Promise<void>}
     */
    async function afterCvRun(roleId, run) {
        if (state.activeRoleId !== roleId) {
            return;
        }
        try {
            await loadRuns(roleId, { selectRunId: run && run.runId });
        } catch (err) {
            setStatus(`Couldn't reload the run history: ${err.message}`, true);
        }
    }

    return {
        loadRuns,
        showSelectedRun,
        handleRunSelectChanged,
        refreshTailoredOutput,
        afterCvRun,
    };
}
