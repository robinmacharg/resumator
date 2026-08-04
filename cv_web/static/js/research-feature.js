import { parseResearchUrlsInput, sleep } from "./app-utils.js";

export function createResearchFeature(ctx) {
    const {
        state,
        els,
        api,
        currentFiles,
        writeDraftToLocalStorage,
        setStatus,
        setResearchRunning,
        updatePreviewCacheBuster,
        updateDiskSnapshot,
        setResearchStatus,
        setResearchOutput,
        setResearchCommandOutput,
        renderResearchState,
        summarizeResearchOutput,
    } = ctx;

    async function fetchResearchStatus() {
        return api("/api/research/status");
    }

    async function waitForResearchCompletion() {
        while (true) {
            const status = await fetchResearchStatus();
            const run = status.run || null;
            if (run) {
                setResearchOutput(summarizeResearchOutput(run));
                setResearchCommandOutput(run.command || []);
                if (status.running) {
                    setResearchStatus(`Research running (${run.elapsedSeconds || 0}s)...`);
                }
            }

            if (!status.running) {
                return run;
            }

            await sleep(1000);
        }
    }

    async function runResearch() {
        const companyName = (els.researchCompanyInput.value || "").trim();
        if (!companyName) {
            setStatus("Company name is required for research run.", true);
            setResearchStatus("Company name is required.", true);
            return;
        }

        const researchPrompt = (els.researchPromptEditor.value || "").trim();
        if (!researchPrompt) {
            setStatus(
                "Research prompt is empty. Reset prompt or add content before running.",
                true,
            );
            setResearchStatus("Research prompt is empty.", true);
            setResearchOutput(
                "Research prompt is empty. Use 'Reset Prompt to Default' or enter a custom prompt.",
            );
            return;
        }

        const urls = parseResearchUrlsInput(els.researchUrlsInput.value || "");

        setResearchRunning(true);
        setResearchStatus("Starting research run...");
        setResearchOutput("Starting research run...");

        try {
            writeDraftToLocalStorage();
            const kickoff = await api("/api/research/run", {
                method: "POST",
                body: JSON.stringify({
                    files: currentFiles(),
                    companyName,
                    urls,
                    dryRun: Boolean(els.researchDryRunCheckbox.checked),
                    autoFormatPdf: true,
                    selectedProvider: state.selectedProvider || "gemini",
                    selectedModel: state.selectedModel || "",
                }),
            });

            if (kickoff.run) {
                setResearchOutput(summarizeResearchOutput(kickoff.run));
                setResearchCommandOutput(kickoff.run.command || []);
            }

            const run = await waitForResearchCompletion();
            if (run && run.stoppedByUser) {
                setResearchStatus(`Research stopped (${run.elapsedSeconds}s).`);
                setStatus("Research run stopped.");
            } else if (run && run.success) {
                setResearchStatus(`Research complete (${run.elapsedSeconds}s).`);
                setStatus("Research run complete.");
            } else {
                setResearchStatus("Research run failed.", true);
                setStatus("Research run failed. See Research Output.", true);
            }

            const refreshed = await api("/api/research/state");
            renderResearchState(refreshed);
            updatePreviewCacheBuster();
        } catch (err) {
            setResearchStatus(`Research run failed: ${err.message}`, true);
            setResearchOutput(err.stack || err.message);
            setStatus(`Research run failed: ${err.message}`, true);
        } finally {
            setResearchRunning(false);
        }
    }

    async function stopResearch() {
        setResearchStatus("Stopping research run...");
        setStatus("Stopping research run...");

        try {
            await api("/api/research/stop", {
                method: "POST",
                body: JSON.stringify({}),
            });
            setResearchStatus("Stop requested. Waiting for process to exit...");
        } catch (err) {
            setResearchStatus(`Failed to stop research run: ${err.message}`, true);
            setStatus(`Failed to stop research run: ${err.message}`, true);
        }
    }

    function onResearchPrimaryAction() {
        if (state.isResearchRunning) {
            const shouldStop = window.confirm("Stop the current research run?");
            if (!shouldStop) {
                return;
            }
            stopResearch();
            return;
        }
        runResearch();
    }

    async function formatResearchPdf() {
        setResearchRunning(true);
        setResearchStatus("Formatting research PDF...");

        try {
            const kickoff = await api("/api/research/format", {
                method: "POST",
                body: JSON.stringify({}),
            });

            if (kickoff.run) {
                setResearchOutput(summarizeResearchOutput(kickoff.run));
                setResearchCommandOutput(kickoff.run.command || []);
            }

            const run = await waitForResearchCompletion();
            if (run && run.success) {
                setResearchStatus(`Research PDF formatted (${run.elapsedSeconds}s).`);
                setStatus("Research PDF formatting complete.");
            } else {
                setResearchStatus("Research PDF formatting failed.", true);
                setStatus("Research PDF formatting failed. See Research Output.", true);
            }

            const refreshed = await api("/api/research/state");
            renderResearchState(refreshed);
            updatePreviewCacheBuster();
        } catch (err) {
            setResearchStatus(`Research PDF formatting failed: ${err.message}`, true);
            setStatus(`Research PDF formatting failed: ${err.message}`, true);
        } finally {
            setResearchRunning(false);
        }
    }

    async function resetResearchPrompt() {
        const confirmed = window.confirm(
            "Reset research prompt to default? This will overwrite the current research prompt file.",
        );
        if (!confirmed) {
            return;
        }

        setResearchRunning(true);
        setResearchStatus("Resetting prompt to default...");

        try {
            await api("/api/research/reset-prompt", {
                method: "POST",
                body: JSON.stringify({}),
            });

            const disk = await api("/api/state");
            const files = disk.files || {};
            if (typeof files.research_prompt === "string") {
                els.researchPromptEditor.value = files.research_prompt;
                updateDiskSnapshot(files);
                writeDraftToLocalStorage();
            }

            const researchState = await api("/api/research/state");
            renderResearchState(researchState);
            setResearchStatus("Prompt reset to default.");
            setStatus("Research prompt reset from default file.");
        } catch (err) {
            setResearchStatus(`Reset failed: ${err.message}`, true);
            setStatus(`Research prompt reset failed: ${err.message}`, true);
        } finally {
            setResearchRunning(false);
        }
    }

    async function copyResearchOutputToClipboard() {
        const sourceText =
            state.activeResearchOutputTab === "command"
                ? els.researchCommandOutput && els.researchCommandOutput.value
                    ? els.researchCommandOutput.value
                    : ""
                : state.activeResearchOutputTab === "built_query"
                  ? els.researchBuiltQueryOutput && els.researchBuiltQueryOutput.textContent
                      ? els.researchBuiltQueryOutput.textContent
                      : ""
                  : els.researchOutput && els.researchOutput.textContent
                    ? els.researchOutput.textContent
                    : "";

        const text = sourceText.trim();
        if (!text) {
            setResearchStatus("No research output to copy.", true);
            return;
        }

        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const ta = document.createElement("textarea");
                ta.value = text;
                ta.setAttribute("readonly", "");
                ta.style.position = "absolute";
                ta.style.left = "-9999px";
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
            }
            setResearchStatus("Research output copied to clipboard.");
        } catch (err) {
            setResearchStatus(`Copy failed: ${err.message}`, true);
        }
    }

    return {
        fetchResearchStatus,
        waitForResearchCompletion,
        runResearch,
        stopResearch,
        onResearchPrimaryAction,
        formatResearchPdf,
        resetResearchPrompt,
        copyResearchOutputToClipboard,
    };
}
