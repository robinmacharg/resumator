import { sleep } from "./app-utils.js";

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
 * @property {{selectedProvider: string, selectedModel: string}} state Shared app state subset.
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
        while (true) {
            const status = await fetchRunStatus();
            const run = status.run || null;
            if (run) {
                setRunLogOutput(summarizeRun(run));
            }

            if (!status.running) {
                return run;
            }

            await sleep(1000);
        }
    }

    /**
     * Run CV pipeline in full or formatting-only mode.
     * Side effects: updates running state, status timer, logs, preview and disk snapshot.
     * @param {"full" | "format"} kind Pipeline execution mode.
     * @returns {Promise<void>}
     */
    async function runPipeline(kind) {
        setRunning(true);
        startRunStatusTimer(
            kind === "full" ? "Running full pipeline..." : "Running formatting only...",
        );
        setRunLogOutput("Starting run...");

        try {
            writeDraftToLocalStorage();
            const kickoff = await api(kind === "full" ? "/api/run/full" : "/api/run/format", {
                method: "POST",
                body: JSON.stringify({
                    files: currentFiles(),
                    selectedProvider: state.selectedProvider || "gemini",
                    selectedModel: state.selectedModel || "",
                }),
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

    return {
        fetchRunStatus,
        waitForRunCompletion,
        runPipeline,
    };
}
