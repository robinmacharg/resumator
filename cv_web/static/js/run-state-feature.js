/**
 * Architecture role:
 * - Layer: shared workflow-control feature used by app bootstrap.
 * - Responsibility: manage active-run flags, timer lifecycle, and control enable/disable state.
 *
 * Plain-language purpose:
 * - This module is the app's "busy-state controller".
 * - It tracks whether CV/Research operations are running, updates timer text, and keeps action buttons in the correct enabled/disabled state.
 */

/**
 * Dependencies required by run-state feature.
 *
 * @typedef {Object} RunStateFeatureContext
 * @property {any} state Shared app state with running flags and timer fields.
 * @property {any} els DOM element registry for interactive controls.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 */

/**
 * Create run-state feature.
 *
 * @param {RunStateFeatureContext} ctx Feature dependencies.
 * @returns {{startRunStatusTimer: (message: string) => void, stopRunStatusTimer: () => void, setRunning: (running: boolean) => void, setResearchRunning: (running: boolean) => void, syncResearchPrimaryButton: () => void}}
 */
export function createRunStateFeature(ctx) {
    const { state, els, setStatus } = ctx;

    /**
     * Update research primary button label/style based on running state.
     * @returns {void}
     */
    function syncResearchPrimaryButton() {
        if (!els.runResearchBtn) {
            return;
        }

        if (state.isResearchRunning) {
            els.runResearchBtn.textContent = "Stop Research";
            els.runResearchBtn.classList.remove("btn-primary");
            els.runResearchBtn.classList.add("btn-danger");
        } else {
            els.runResearchBtn.textContent = "Run Research";
            els.runResearchBtn.classList.remove("btn-danger");
            els.runResearchBtn.classList.add("btn-primary");
        }
    }

    /**
     * Apply disabled state to app controls during active runs.
     * @returns {void}
     */
    function applyControlDisabledState() {
        const disabled = state.isRunning || state.isResearchRunning;
        [
            els.runFormatBtn,
            els.runFullBtn,
            ...els.fileLoadButtons,
            ...els.fileSaveButtons,
            els.formatResearchBtn,
            els.resetResearchPromptBtn,
            els.copyResearchOutputBtn,
            els.researchCompanyInput,
            els.researchUrlsInput,
            els.researchDryRunCheckbox,
            els.providerSelect,
            els.modelSelect,
            els.themeSelect,
            els.restartServerBtn,
        ].forEach((el) => {
            if (!el) {
                return;
            }
            el.disabled = disabled;
        });

        if (els.runResearchBtn) {
            els.runResearchBtn.disabled = state.isRunning;
        }

        syncResearchPrimaryButton();
    }

    /**
     * Start global run status timer message.
     * @param {string} message Status message prefix.
     * @returns {void}
     */
    function startRunStatusTimer(message) {
        stopRunStatusTimer();
        state.runStatusMessage = message;
        state.runStatusStartMs = Date.now();

        const render = () => {
            const elapsedSeconds = Math.floor((Date.now() - state.runStatusStartMs) / 1000);
            setStatus(`${state.runStatusMessage} [${elapsedSeconds}s]`);
        };

        render();
        state.runStatusTimerId = window.setInterval(render, 1000);
    }

    /**
     * Stop and clear global run status timer state.
     * @returns {void}
     */
    function stopRunStatusTimer() {
        if (state.runStatusTimerId !== null) {
            clearInterval(state.runStatusTimerId);
            state.runStatusTimerId = null;
        }
        state.runStatusStartMs = 0;
        state.runStatusMessage = "";
    }

    /**
     * Set CV run active state.
     * @param {boolean} running
     * @returns {void}
     */
    function setRunning(running) {
        state.isRunning = running;
        applyControlDisabledState();
    }

    /**
     * Set research run active state.
     * @param {boolean} running
     * @returns {void}
     */
    function setResearchRunning(running) {
        state.isResearchRunning = running;
        applyControlDisabledState();
    }

    return {
        startRunStatusTimer,
        stopRunStatusTimer,
        setRunning,
        setResearchRunning,
        syncResearchPrimaryButton,
    };
}
