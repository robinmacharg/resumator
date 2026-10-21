import { pollUntilDone } from "./async-workflow-utils.js";

/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap.
 * - Responsibility: run CV pipeline operations (format/full), poll run status, and coordinate downstream refreshes.
 *
 * Plain-language purpose:
 * - This module is the "run engine" for CV generation. It starts runs and keeps status/log/preview synchronized until completion.
 */

/**
 * Dependencies required by the CV pipeline feature.
 * Boundaries: this feature orchestrates CV run polling and status updates, but does not own DOM queries.
 * Side effects are performed via injected callbacks.
 *
 * @typedef {Object} CvPipelineFeatureContext
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API request helper.
 * @property {() => {cv: string, prompt: string, research_prompt: string, jobspec: string, env: string}} currentFiles Current editor payload.
 * @property {() => void} writeDraftToLocalStorage Persist current draft before runs.
 * @property {{selectedProvider: string, selectedModel: string, selectedTheme?: string}} state Shared app state subset.
 * @property {(running: boolean) => void} setRunning Toggle global running state.
 * @property {(message: string) => void} startRunStatusTimer Start status timer message.
 * @property {() => void} stopRunStatusTimer Stop run status timer.
 * @property {(text: string) => void} setRunLogOutput Render run output text.
 * @property {(message: string, isError?: boolean) => void} setStatus Render status text.
 * @property {(files: any) => void} updateDiskSnapshot Refresh local disk snapshot for dirty checks.
 * @property {(payload: any) => void} applyCvOutputState Update preview output state from API payload.
 * @property {() => void} updatePreviewCacheBuster Refresh preview iframe/source metadata.
 * @property {() => Promise<void>} refreshTailoredOutput Refresh tailored markdown output.
 * @property {() => Promise<void>} refreshLogs Refresh logs UI.
 * @property {(run: any) => string} summarizeRun Convert run payload to display text.
 * @property {() => {enabled: boolean, text: string}} [getSteeringRequest] Steering for full runs.
 * @property {() => number | null} [getActiveRoleId] Role mode: the active role, or null for file mode.
 * @property {() => Promise<void>} [saveRoleEditsBeforeRun] Role mode: save unsaved role edits first.
 * @property {(roleId: number, run: any) => Promise<void>} [afterRoleCvRun] Role mode: reload the run history.
 */

/**
 * Create the CV pipeline feature.
 * Purpose: execute format/full CV pipeline runs and keep run status/log/preview synchronized.
 * Boundary: no direct DOM lookup; all rendering and state mutations are done through injected callbacks.
 *
 * @param {CvPipelineFeatureContext} ctx Feature dependencies.
 * @returns {{fetchRunStatus: () => Promise<any>, waitForRunCompletion: () => Promise<any>, runPipeline: (kind: "full" | "format") => Promise<void>}} Public CV pipeline API.
 */
export function createCvPipelineFeature(ctx) {
    const {
        api,
        currentFiles,
        writeDraftToLocalStorage,
        state,
        setRunning,
        startRunStatusTimer,
        stopRunStatusTimer,
        setRunLogOutput,
        setStatus,
        updateDiskSnapshot,
        applyCvOutputState,
        updatePreviewCacheBuster,
        refreshTailoredOutput,
        refreshLogs,
        summarizeRun,
        getSteeringRequest,
        getActiveRoleId,
        saveRoleEditsBeforeRun,
        afterRoleCvRun,
    } = ctx;

    /**
     * Fetch current CV run status payload.
     * @returns {Promise<any>} Server run status envelope.
     */
    async function fetchRunStatus() {
        return api("/api/run/status");
    }

    /**
     * Poll run status until completion.
     * Side effects: pushes summarized output to run log while running.
     * @returns {Promise<any>} Final run payload.
     */
    async function waitForRunCompletion() {
        const finalStatus = await pollUntilDone({
            fetchStatus: fetchRunStatus,
            isRunning: (status) => Boolean(status && status.running),
            onTick: (status) => {
                const run = status.run || null;
                if (run) {
                    setRunLogOutput(summarizeRun(run));
                }
            },
            intervalMs: 1000,
        });

        return finalStatus.run || null;
    }

    /**
     * Run CV pipeline in full or formatting-only mode.
     * Side effects: updates running state, status timer, logs, preview and disk snapshot.
     * @param {"full" | "format"} kind Pipeline execution mode.
     * @returns {Promise<void>}
     */
    async function runPipeline(kind) {
        const roleId = getActiveRoleId ? getActiveRoleId() : null;
        if (roleId !== null) {
            await runRolePipeline(roleId);
            return;
        }
        setRunning(true);
        startRunStatusTimer(
            kind === "full" ? "Running full pipeline..." : "Running formatting only...",
        );
        setRunLogOutput("Starting run...");

        try {
            writeDraftToLocalStorage();
            const body = {
                files: currentFiles(),
                selectedProvider: state.selectedProvider || "gemini",
                selectedModel: state.selectedModel || "",
                selectedTheme: state.selectedTheme || "",
            };
            if (kind === "full" && getSteeringRequest) {
                body.steering = getSteeringRequest();
            }
            const kickoff = await api(kind === "full" ? "/api/run/full" : "/api/run/format", {
                method: "POST",
                body: JSON.stringify(body),
            });
            if (kickoff.run) {
                setRunLogOutput(summarizeRun(kickoff.run));
            }

            const run = await waitForRunCompletion();

            const refreshedState = await api("/api/state");
            if (refreshedState.files) {
                updateDiskSnapshot(refreshedState.files);
            }
            applyCvOutputState(refreshedState);

            updatePreviewCacheBuster();
            await refreshTailoredOutput();
            await refreshLogs();

            stopRunStatusTimer();
            if (run && run.success) {
                setStatus(`Run complete (${run.elapsedSeconds}s).`);
            } else {
                setStatus("Run failed. Open logs for details.", true);
            }
        } catch (err) {
            stopRunStatusTimer();
            setStatus(`Run failed: ${err.message}`, true);
            setRunLogOutput(err.stack || err.message);
        } finally {
            stopRunStatusTimer();
            setRunning(false);
        }
    }

    /**
     * Role mode: save the role's edits, then start a stored role CV run (`POST /api/roles/<id>/runs/cv`) and poll
     * the shared run status. There is no format-only run: role PDFs render on demand.
     * Steering is sent as shown (role-saved steering may still be debouncing); the theme is the role's.
     * @param {number} roleId
     * @returns {Promise<void>}
     */
    async function runRolePipeline(roleId) {
        setRunning(true);
        startRunStatusTimer("Running full pipeline for this role...");
        setRunLogOutput("Starting run...");

        try {
            writeDraftToLocalStorage();
            if (saveRoleEditsBeforeRun) {
                await saveRoleEditsBeforeRun();
            }
            const steering = getSteeringRequest ? getSteeringRequest() : null;
            const kickoff = await api(`/api/roles/${roleId}/runs/cv`, {
                method: "POST",
                body: JSON.stringify({
                    selectedProvider: state.selectedProvider || "gemini",
                    selectedModel: state.selectedModel || "",
                    theme: null,
                    steering: steering ? steering.text : null,
                }),
            });
            if (kickoff.run) {
                setRunLogOutput(summarizeRun(kickoff.run));
            }

            const run = await waitForRunCompletion();
            if (afterRoleCvRun) {
                await afterRoleCvRun(roleId, run);
            }
            await refreshLogs();

            stopRunStatusTimer();
            if (run && run.success) {
                setStatus(`Run complete (${run.elapsedSeconds}s), saved as run #${run.runId}.`);
            } else {
                const reason = run && run.error ? `: ${run.error}` : ". Open logs for details.";
                setStatus(`Run failed${reason}`, true);
            }
        } catch (err) {
            stopRunStatusTimer();
            setStatus(`Run failed: ${err.message}`, true);
            setRunLogOutput(err.stack || err.message);
        } finally {
            stopRunStatusTimer();
            setRunning(false);
        }
    }

    return {
        fetchRunStatus,
        waitForRunCompletion,
        runPipeline,
    };
}
