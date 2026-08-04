/**
 * Architecture role:
 * - Layer: shared presentation feature used by app bootstrap.
 * - Responsibility: render status/log/research outputs and manage smart auto-scroll behavior.
 *
 * Plain-language purpose:
 * - This module is the app's "output and status renderer".
 * - It decides what text appears in run logs and research panes, and prevents auto-scroll from fighting the user when they scroll up.
 */

/**
 * Dependencies required by output display feature.
 *
 * @typedef {Object} OutputDisplayFeatureContext
 * @property {any} state Shared app state containing active log/research output tab values.
 * @property {any} els DOM element registry for status, log, and research output elements.
 * @property {(command: any) => string} formatCommandForDisplay Command formatting helper.
 * @property {(value: any) => string} formatTimestampToSecond Timestamp formatting helper.
 * @property {(payload: any) => void} applyResearchPreviewState Callback to update research preview metadata.
 */

/**
 * Create output display feature.
 *
 * @param {OutputDisplayFeatureContext} ctx Feature dependencies.
 * @returns {{setStatus: (message: string, isError?: boolean) => void, updateAutoScrollIndicators: () => void, setRunLogOutput: (text: string) => void, setDebugLogOutput: (text: string) => void, setResearchStatus: (message: string, isError?: boolean) => void, setResearchOutput: (text: string) => void, setResearchBuiltQueryOutput: (text: string) => void, setResearchCommandOutput: (command: any) => void, summarizeRun: (run: any) => string, summarizeResearchOutput: (run: any) => string, renderResearchState: (payload: any) => void}}
 */
export function createOutputDisplayFeature(ctx) {
    const {
        state,
        els,
        formatCommandForDisplay,
        formatTimestampToSecond,
        applyResearchPreviewState,
    } = ctx;

    const AUTO_SCROLL_BOTTOM_TOLERANCE_PX = 6;
    const autoScrollTrackerByEl = new WeakMap();

    /**
     * Ensure a scroll tracker exists for an output element.
     * @param {HTMLElement | null} el Output element.
     * @returns {{hasUserScrolled: boolean, programmaticScrollInProgress: boolean} | null}
     */
    function getAutoScrollTracker(el) {
        if (!el) {
            return null;
        }
        let tracker = autoScrollTrackerByEl.get(el);
        if (tracker) {
            return tracker;
        }

        tracker = { hasUserScrolled: false, programmaticScrollInProgress: false };
        el.addEventListener("scroll", () => {
            if (tracker.programmaticScrollInProgress) {
                return;
            }
            tracker.hasUserScrolled = true;
            updateAutoScrollIndicators();
        });
        autoScrollTrackerByEl.set(el, tracker);
        return tracker;
    }

    /**
     * Check whether output element is currently at the bottom.
     * @param {HTMLElement | null} el Output element.
     * @returns {boolean}
     */
    function isAtBottom(el) {
        if (!el) {
            return true;
        }
        const distanceFromBottom = el.scrollHeight - el.clientHeight - el.scrollTop;
        return distanceFromBottom <= AUTO_SCROLL_BOTTOM_TOLERANCE_PX;
    }

    /**
     * Determine if smart auto-scroll should be considered paused for a target output.
     * @param {HTMLElement | null} el Output element.
     * @returns {boolean}
     */
    function isAutoscrollPaused(el) {
        const tracker = getAutoScrollTracker(el);
        return Boolean(tracker && tracker.hasUserScrolled && !isAtBottom(el));
    }

    /**
     * Update visual indicator text for auto-scroll pause state.
     * @param {HTMLElement | null} el Indicator element.
     * @param {boolean} paused Whether auto-scroll is paused.
     * @returns {void}
     */
    function setAutoscrollIndicator(el, paused) {
        if (!el) {
            return;
        }
        const nextText = paused ? "Auto-scroll paused" : "";
        el.textContent = nextText;
        el.classList.toggle("visible", paused);
        el.setAttribute("aria-hidden", paused ? "false" : "true");
    }

    /**
     * Resolve currently active research output element for auto-scroll indicator logic.
     * @returns {HTMLElement | null}
     */
    function getActiveResearchOutputElement() {
        if (state.activeResearchOutputTab === "built_query") {
            return els.researchBuiltQueryOutput;
        }
        if (state.activeResearchOutputTab === "command") {
            return els.researchCommandOutput;
        }
        return els.researchOutput;
    }

    /**
     * Resolve currently active log output element for auto-scroll indicator logic.
     * @returns {HTMLElement | null}
     */
    function getActiveLogElement() {
        if (state.activeLogTab === "debug") {
            return els.debugLogOutput;
        }
        return els.runLogOutput;
    }

    /**
     * Refresh auto-scroll indicator state for active research/log outputs.
     * @returns {void}
     */
    function updateAutoScrollIndicators() {
        setAutoscrollIndicator(
            els.researchAutoscrollIndicator,
            isAutoscrollPaused(getActiveResearchOutputElement()),
        );
        setAutoscrollIndicator(
            els.logsAutoscrollIndicator,
            isAutoscrollPaused(getActiveLogElement()),
        );
    }

    /**
     * Write output text while respecting user scroll position.
     * @param {HTMLElement | null} el Output element.
     * @param {string} text Text content to apply.
     * @param {boolean} [useValueProperty=false] Write to value instead of textContent.
     * @returns {void}
     */
    function setOutputContentWithSmartAutoscroll(el, text, useValueProperty = false) {
        if (!el) {
            return;
        }

        const tracker = getAutoScrollTracker(el);
        const shouldAutoscroll = !tracker || !tracker.hasUserScrolled || isAtBottom(el);

        if (useValueProperty) {
            el.value = text;
        } else {
            el.textContent = text;
        }

        if (!shouldAutoscroll || !tracker) {
            updateAutoScrollIndicators();
            return;
        }

        tracker.programmaticScrollInProgress = true;
        el.scrollTop = el.scrollHeight;
        requestAnimationFrame(() => {
            tracker.programmaticScrollInProgress = false;
            updateAutoScrollIndicators();
        });
    }

    /**
     * Render global status line.
     * @param {string} message Status message.
     * @param {boolean} [isError=false] Error styling toggle.
     * @returns {void}
     */
    function setStatus(message, isError = false) {
        if (!els.statusText) {
            return;
        }
        els.statusText.textContent = message;
        els.statusText.style.color = isError ? "#b42318" : "#1f1f1f";
    }

    /**
     * Render run log output with smart auto-scroll.
     * @param {string} text Run output text.
     * @returns {void}
     */
    function setRunLogOutput(text) {
        setOutputContentWithSmartAutoscroll(els.runLogOutput, text);
    }

    /**
     * Render debug log output with smart auto-scroll.
     * @param {string} text Debug output text.
     * @returns {void}
     */
    function setDebugLogOutput(text) {
        setOutputContentWithSmartAutoscroll(els.debugLogOutput, text);
    }

    /**
     * Render research status line.
     * @param {string} message Status message.
     * @param {boolean} [isError=false] Error styling toggle.
     * @returns {void}
     */
    function setResearchStatus(message, isError = false) {
        if (!els.researchStatusText) {
            return;
        }
        els.researchStatusText.textContent = message;
        els.researchStatusText.style.color = isError ? "#b42318" : "#57534e";
    }

    /**
     * Render research console output.
     * @param {string} text Output text.
     * @returns {void}
     */
    function setResearchOutput(text) {
        if (!els.researchOutput) {
            return;
        }
        setOutputContentWithSmartAutoscroll(els.researchOutput, text);
    }

    /**
     * Render built-query preview output.
     * @param {string} text Output text.
     * @returns {void}
     */
    function setResearchBuiltQueryOutput(text) {
        if (!els.researchBuiltQueryOutput) {
            return;
        }
        setOutputContentWithSmartAutoscroll(els.researchBuiltQueryOutput, text);
    }

    /**
     * Render research command output.
     * @param {any} command Command payload.
     * @returns {void}
     */
    function setResearchCommandOutput(command) {
        if (!els.researchCommandOutput) {
            return;
        }
        const rendered = Array.isArray(command)
            ? formatCommandForDisplay(command)
            : String(command || "");
        setOutputContentWithSmartAutoscroll(
            els.researchCommandOutput,
            rendered || "No command yet. Run Research first.",
            true,
        );
    }

    /**
     * Summarize CV run payload into user-readable text.
     * @param {any} run Run payload.
     * @returns {string}
     */
    function summarizeRun(run) {
        if (!run || typeof run !== "object") {
            return "No run output yet.";
        }

        const isRunning = Boolean(run.running);
        const exitDisplay =
            run.exitCode === null || run.exitCode === undefined ? "running" : run.exitCode;
        const elapsedDisplay =
            run.elapsedSeconds === null || run.elapsedSeconds === undefined
                ? "-"
                : `${run.elapsedSeconds}s`;

        const summary = [
            `Kind: ${run.kind}`,
            `Exit: ${exitDisplay}`,
            `Elapsed: ${elapsedDisplay}`,
            `Status: ${isRunning ? "running" : run.success ? "success" : "failed"}`,
            "",
        ];

        if (run.output) {
            summary.push(run.output);
        } else {
            summary.push("(No process output)");
        }

        return summary.join("\n");
    }

    /**
     * Summarize research run payload into user-readable text.
     * @param {any} run Research run payload.
     * @returns {string}
     */
    function summarizeResearchOutput(run) {
        if (!run) {
            return "No research run output yet.";
        }
        const status = run.running
            ? "running"
            : run.stoppedByUser
              ? "stopped"
              : run.success
                ? "success"
                : "failed";
        const elapsed =
            run.elapsedSeconds === null || run.elapsedSeconds === undefined
                ? "-"
                : `${run.elapsedSeconds}s`;
        const exit = run.exitCode === null || run.exitCode === undefined ? "running" : run.exitCode;

        const operation = run.kind === "research_format" ? "format" : "research";
        const company = run.kind === "research_format" ? "(n/a)" : run.companyName || "(unknown)";

        const lines = [
            `Operation: ${operation}`,
            `Company: ${company}`,
            `Status: ${status}`,
            `Exit: ${exit}`,
            `Elapsed: ${elapsed}`,
            `Dry Run: ${run.dryRun ? "yes" : "no"}`,
            run.autoFormatPdf ? "Auto Format PDF: enabled" : "Auto Format PDF: disabled",
            run.formatAttempted === true
                ? `Format Exit: ${run.formatExitCode === null || run.formatExitCode === undefined ? "-" : run.formatExitCode}`
                : null,
            run.formatAttempted === true
                ? `Format Status: ${run.formatSuccess ? "success" : "failed"}`
                : null,
            run.success
                ? `Generated At: ${formatTimestampToSecond(run.finishedAt || run.startedAt)}`
                : null,
            "",
            run.output || "(No process output)",
        ].filter((line) => line !== null);
        return lines.join("\n");
    }

    /**
     * Render research state payload to related UI outputs.
     * @param {any} payload Research state payload.
     * @returns {void}
     */
    function renderResearchState(payload) {
        if (!payload || typeof payload !== "object") {
            return;
        }

        applyResearchPreviewState(payload);

        if (typeof payload.companyName === "string") {
            els.researchCompanyInput.value = payload.companyName;
        }

        if (Array.isArray(payload.urls)) {
            els.researchUrlsInput.value = payload.urls.join("\n");
        }

        const output = payload.output || {};
        if (typeof output.builtPrompt === "string" && output.builtPrompt.trim()) {
            setResearchBuiltQueryOutput(output.builtPrompt);
        } else {
            setResearchBuiltQueryOutput("No built query yet. Run Research first.");
        }

        if (typeof output.markdown === "string" && output.markdown.trim()) {
            setResearchOutput(output.markdown);
        } else if (typeof output.json === "string" && output.json.trim()) {
            setResearchOutput(output.json);
        }

        if (payload.lastRun) {
            setResearchOutput(summarizeResearchOutput(payload.lastRun));
            setResearchCommandOutput(payload.lastRun.command || []);
        } else {
            setResearchCommandOutput([]);
        }
    }

    return {
        setStatus,
        updateAutoScrollIndicators,
        setRunLogOutput,
        setDebugLogOutput,
        setResearchStatus,
        setResearchOutput,
        setResearchBuiltQueryOutput,
        setResearchCommandOutput,
        summarizeRun,
        summarizeResearchOutput,
        renderResearchState,
    };
}
