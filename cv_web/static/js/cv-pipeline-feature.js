import { sleep } from "./app-utils.js";

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

    async function fetchRunStatus() {
        return api("/api/run/status");
    }

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
