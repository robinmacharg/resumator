import { pollUntilDone, runWithStatusOperation } from "./async-workflow-utils.js";
import { parseResearchUrlsInput } from "./app-utils.js";

/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap.
 * - Responsibility: execute research workflows (run/stop/format/reset) and keep research outputs current.
 *
 * Plain-language purpose:
 * - This module is the "research operator". It takes research inputs, runs the backend process, and streams results into the UI.
 */

/**
 * Dependencies required by the research feature.
 * Boundaries: this feature orchestrates research lifecycle and polling; UI/state mutations are delegated to callbacks.
 *
 * @typedef {Object} ResearchFeatureContext
 * @property {{isResearchRunning: boolean, selectedProvider: string, selectedModel: string, activeResearchOutputTab: string, researchRuns?: any[], roles?: any[]}} state Shared app state subset.
 * @property {any} els DOM element registry.
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API request helper.
 * @property {() => {cv: string, prompt: string, research_prompt: string, jobspec: string}} currentFiles Current editor payload.
 * @property {() => void} writeDraftToLocalStorage Persist draft before operations.
 * @property {(message: string, isError?: boolean) => void} setStatus Global status renderer.
 * @property {(running: boolean) => void} setResearchRunning Toggle research-running UI state.
 * @property {() => void} updatePreviewCacheBuster Refresh preview metadata/source.
 * @property {(files: any) => void} updateDiskSnapshot Refresh disk snapshot for dirty indicators.
 * @property {(message: string, isError?: boolean) => void} setResearchStatus Research status renderer.
 * @property {(text: string) => void} setResearchOutput Research console renderer.
 * @property {(command: any) => void} setResearchCommandOutput Research command renderer.
 * @property {(payload: any) => void} renderResearchState Apply research state to UI.
 * @property {(run: any) => string} summarizeResearchOutput Convert run payload to display text.
 * @property {() => number | null} [getActiveRoleId] Role mode: the active role, or null for file mode.
 * @property {() => boolean} [isRoleRequired] Role mode with no role yet: runs are refused.
 * @property {() => Promise<void>} [saveRoleEditsBeforeRun] Role mode: save unsaved edits first.
 * @property {(roleId: number, run: any) => Promise<void>} [afterRoleResearchRun] Role mode: after a stored run.
 * @property {(source: any) => void} [setResearchRunSource] Role mode: Research preview source (null = file mode).
 * @property {(text: string) => void} [setResearchBuiltQueryOutput] Built-query pane renderer.
 * @property {(iso: string) => string} [formatDateTime] Short date-time formatter for the run picker.
 */

/**
 * Create the research feature.
 * Purpose: run/stop/format/reset research workflows, poll status, and synchronize output panels.
 * Boundary: no direct DOM querying; consumes pre-collected element references and callback functions.
 *
 * @param {ResearchFeatureContext} ctx Feature dependencies.
 * @returns {{fetchResearchStatus: () => Promise<any>, waitForResearchCompletion: () => Promise<any>, runResearch: () => Promise<void>, stopResearch: () => Promise<void>, onResearchPrimaryAction: () => void, formatResearchPdf: () => Promise<void>, resetResearchPrompt: () => Promise<void>, copyResearchOutputToClipboard: () => Promise<void>, loadRoleResearch: (roleId: number | null, options?: {keepConsole?: boolean}) => Promise<void>, handleResearchRunSelectChanged: () => Promise<void>}}
 */
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
        getActiveRoleId,
        isRoleRequired,
        saveRoleEditsBeforeRun,
        afterRoleResearchRun,
        setResearchRunSource,
        setResearchBuiltQueryOutput,
        formatDateTime,
    } = ctx;

    /**
     * Fetch current research status payload.
     * @returns {Promise<any>} Server research status envelope.
     */
    async function fetchResearchStatus() {
        return api("/api/research/status");
    }

    /**
     * Poll research status until completion.
     * Side effects: keeps output and command panes live-updated during execution.
     * @returns {Promise<any>} Final research run payload.
     */
    async function waitForResearchCompletion() {
        const finalStatus = await pollUntilDone({
            fetchStatus: fetchResearchStatus,
            isRunning: (status) => Boolean(status && status.running),
            onTick: (status) => {
                const run = status.run || null;
                if (run) {
                    setResearchOutput(summarizeResearchOutput(run));
                    setResearchCommandOutput(run.command || []);
                    if (status.running) {
                        setResearchStatus(`Research running (${run.elapsedSeconds || 0}s)...`);
                    }
                }
            },
            intervalMs: 1000,
        });

        return finalStatus.run || null;
    }

    /**
     * Start a research run from current UI inputs.
     * Validates company name and prompt, persists draft, then runs and polls until completion.
     * @returns {Promise<void>}
     */
    async function runResearch() {
        const roleId = getActiveRoleId ? getActiveRoleId() : null;
        if (roleId === null && isRoleRequired && isRoleRequired()) {
            setStatus("Runs belong to a role: add one with + first.", true);
            setResearchStatus("Runs belong to a role: add one with + first.", true);
            return;
        }
        const companyName = (els.researchCompanyInput.value || "").trim();
        if (!companyName && roleId === null) {
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
            const kickoff =
                roleId === null
                    ? await api("/api/research/run", {
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
                      })
                    : await startRoleResearch(roleId, companyName, urls);

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

            if (roleId === null) {
                const refreshed = await api("/api/research/state");
                renderResearchState(refreshed);
                updatePreviewCacheBuster();
            } else {
                // A failed or stopped run isn't stored as current: keep its log in the console.
                if (getActiveRoleId() === roleId) {
                    await loadRoleResearch(roleId, { keepConsole: !(run && run.success) });
                }
                if (afterRoleResearchRun) {
                    await afterRoleResearchRun(roleId, run);
                }
            }
        } catch (err) {
            setResearchStatus(`Research run failed: ${err.message}`, true);
            setResearchOutput(err.stack || err.message);
            setStatus(`Research run failed: ${err.message}`, true);
        } finally {
            setResearchRunning(false);
        }
    }

    /**
     * Role mode: save unsaved edits (the research prompt is still a file), then start a stored role research run.
     * An empty company uses the role's. Progress comes from the shared `/api/research/status`.
     * @param {number} roleId
     * @param {string} companyName
     * @param {string[]} urls
     * @returns {Promise<any>} Kickoff payload.
     */
    async function startRoleResearch(roleId, companyName, urls) {
        if (saveRoleEditsBeforeRun) {
            await saveRoleEditsBeforeRun();
        }
        return api(`/api/roles/${roleId}/runs/research`, {
            method: "POST",
            body: JSON.stringify({
                selectedProvider: state.selectedProvider || "gemini",
                selectedModel: state.selectedModel || "",
                company: companyName || null,
                urls,
                dryRun: Boolean(els.researchDryRunCheckbox.checked),
            }),
        });
    }

    /**
     * Show a research run's text in the output panes, or a placeholder (role mode).
     * @param {string} consoleText Console pane text.
     * @param {string} builtQuery Built-query pane text.
     * @returns {void}
     */
    function showRoleResearchText(consoleText, builtQuery) {
        setResearchOutput(consoleText);
        if (setResearchBuiltQueryOutput) {
            setResearchBuiltQueryOutput(builtQuery);
        }
        setResearchCommandOutput([]);
    }

    /**
     * Picker label: "#3 · 21 Oct 14:02 · gemini/pro · ✓ · dry run · current".
     * @param {any} run
     * @returns {string}
     */
    function researchRunLabel(run) {
        const model = [run.provider, run.model].filter(Boolean).join("/");
        return [
            `#${run.id}`,
            formatDateTime ? formatDateTime(run.finishedAt || run.startedAt) : run.finishedAt || run.startedAt,
            model,
            run.success ? "✓" : "✗",
            run.dryRun ? "dry run" : "",
            run.isCurrent ? "current" : "",
        ]
            .filter(Boolean)
            .join(" · ");
    }

    /**
     * Fill the research run picker from state.researchRuns; failed runs can't be picked.
     * @returns {void}
     */
    function renderResearchRunSelect() {
        const select = els.researchRunSelect;
        if (!select) {
            return;
        }
        select.replaceChildren();
        const runs = state.researchRuns || [];
        if (!runs.length) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No runs yet";
            select.appendChild(opt);
            return;
        }
        runs.forEach((run) => {
            const opt = document.createElement("option");
            opt.value = String(run.id);
            opt.textContent = researchRunLabel(run);
            opt.disabled = !run.success;
            select.appendChild(opt);
        });
        const current = runs.find((run) => run.isCurrent);
        select.value = current ? String(current.id) : "";
    }

    /**
     * Prefill company and URLs from the current run; the company falls back to the role's (RR5).
     * @param {number} roleId
     * @param {any | null} current Current run summary, or null.
     * @returns {void}
     */
    function prefillResearchInputs(roleId, current) {
        const role = (state.roles || []).find((item) => item.id === roleId);
        els.researchCompanyInput.value = (current && current.company) || (role && role.company) || "";
        const urls = current && Array.isArray(current.urlsJson) ? current.urlsJson : [];
        els.researchUrlsInput.value = urls.join("\n");
    }

    /**
     * Role mode: show the role's current research run (output and PDF), never `output/` files (RR4), fill the run
     * picker and prefill company and URLs (RR5). With no role or no current run, the panes and preview show an
     * empty state.
     * @param {number | null} roleId Active role, or null when there is none yet.
     * @param {{keepConsole?: boolean}} [options] keepConsole leaves the output panes and inputs alone (a failed
     *   run's log, and the inputs it was started with).
     * @returns {Promise<void>}
     */
    async function loadRoleResearch(roleId, options = {}) {
        const empty = (label, placeholder) => {
            if (setResearchRunSource) {
                setResearchRunSource({ url: null, label, generatedAt: null, placeholder });
            }
            if (!options.keepConsole) {
                showRoleResearchText(placeholder, placeholder);
            }
            updatePreviewCacheBuster();
        };
        if (roleId === null) {
            state.researchRuns = [];
            renderResearchRunSelect();
            empty("no role yet", "No role yet: add one with +");
            return;
        }
        try {
            const { researchRuns } = await api(`/api/roles/${roleId}/runs`);
            if (getActiveRoleId && getActiveRoleId() !== roleId) {
                return;
            }
            state.researchRuns = researchRuns || [];
            renderResearchRunSelect();
            const current = state.researchRuns.find((item) => item.isCurrent) || null;
            if (!options.keepConsole) {
                prefillResearchInputs(roleId, current);
            }
            if (!current) {
                empty("no runs yet", "No research runs yet for this role. Run Research first.");
                return;
            }
            const { run } = await api(`/api/roles/${roleId}/runs/research/${current.id}`);
            if (getActiveRoleId && getActiveRoleId() !== roleId) {
                return;
            }
            const markdown = (run.outputMd || "").trim();
            const json = run.outputJson || {};
            if (setResearchRunSource) {
                setResearchRunSource({
                    url: markdown ? `/api/roles/${roleId}/runs/research/${run.id}/research.pdf` : null,
                    label: `run #${run.id}`,
                    generatedAt: run.finishedAt || run.startedAt,
                    placeholder: `Run #${run.id} has no output${run.dryRun ? " (dry run)" : ""}.`,
                });
            }
            if (!options.keepConsole) {
                showRoleResearchText(
                    markdown || json.output || `Run #${run.id} has no output.`,
                    json.promptPreview || "No built query stored for this run.",
                );
            }
            updatePreviewCacheBuster();
        } catch (err) {
            setResearchStatus(`Couldn't load the role's research: ${err.message}`, true);
        }
    }

    /**
     * Research run picker change: make the picked run current, then show it.
     * @returns {Promise<void>}
     */
    async function handleResearchRunSelectChanged() {
        const roleId = getActiveRoleId ? getActiveRoleId() : null;
        const runId = Number(els.researchRunSelect && els.researchRunSelect.value);
        if (roleId === null || !Number.isFinite(runId) || runId <= 0) {
            return;
        }
        try {
            await api(`/api/roles/${roleId}/runs/research/${runId}/current`, {
                method: "POST",
                body: JSON.stringify({}),
            });
            await loadRoleResearch(roleId);
            setResearchStatus(`Showing research run #${runId}.`);
        } catch (err) {
            setResearchStatus(`Couldn't select research run #${runId}: ${err.message}`, true);
            renderResearchRunSelect();
        }
    }

    /**
     * Request stop for active research run.
     * @returns {Promise<void>}
     */
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

    /**
     * Primary research button behavior.
     * Stops active run with confirmation, or starts a new run.
     * @returns {void}
     */
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

    /**
     * Run research formatting workflow for existing research output.
     * @returns {Promise<void>}
     */
    async function formatResearchPdf() {
        setResearchRunning(true);

        await runWithStatusOperation({
            setStatus: setResearchStatus,
            startMessage: "Formatting research PDF...",
            errorPrefix: "Research PDF formatting failed",
            operation: async () => {
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
            },
            onError: (err) => {
                setStatus(`Research PDF formatting failed: ${err.message}`, true);
            },
            onFinally: () => {
                setResearchRunning(false);
            },
        });
    }

    /**
     * Reset research prompt from default server-side file.
     * @returns {Promise<void>}
     */
    async function resetResearchPrompt() {
        const confirmed = window.confirm(
            "Reset research prompt to default? This will overwrite the current research prompt file.",
        );
        if (!confirmed) {
            return;
        }

        setResearchRunning(true);

        await runWithStatusOperation({
            setStatus: setResearchStatus,
            startMessage: "Resetting prompt to default...",
            errorPrefix: "Reset failed",
            operation: async () => {
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
            },
            onError: (err) => {
                setStatus(`Research prompt reset failed: ${err.message}`, true);
            },
            onFinally: () => {
                setResearchRunning(false);
            },
        });
    }

    /**
     * Copy the active research output pane content to clipboard.
     * @returns {Promise<void>}
     */
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
        loadRoleResearch,
        handleResearchRunSelectChanged,
    };
}
