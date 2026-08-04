/**
 * Architecture role:
 * - Layer: composition support feature used by app bootstrap.
 * - Responsibility: attach DOM event handlers to composed feature APIs.
 *
 * Plain-language purpose:
 * - This module is the app's "event wiring map".
 * - It connects buttons and UI controls to the feature functions that implement behavior.
 */

/**
 * Dependencies required by app event-bindings feature.
 *
 * @typedef {Object} AppEventBindingsFeatureContext
 * @property {any} els DOM element registry.
 * @property {any} cvPipelineFeature CV pipeline feature API.
 * @property {any} appOperationsFeature App operations feature API.
 * @property {any} researchFeature Research feature API.
 * @property {any} logsFeature Logs feature API.
 * @property {any} uiLayoutFeature UI layout feature API.
 * @property {any} providerModelFeature Provider/model feature API.
 */

/**
 * Create app event-bindings feature.
 *
 * @param {AppEventBindingsFeatureContext} ctx Feature dependencies.
 * @returns {{bindEventHandlers: () => void}}
 */
export function createAppEventBindingsFeature(ctx) {
    const {
        els,
        cvPipelineFeature,
        appOperationsFeature,
        researchFeature,
        logsFeature,
        uiLayoutFeature,
        providerModelFeature,
    } = ctx;

    /**
     * Attach event handlers for all interactive controls.
     * @returns {void}
     */
    function bindEventHandlers() {
        els.runFormatBtn.addEventListener("click", () => cvPipelineFeature.runPipeline("format"));
        els.runFullBtn.addEventListener("click", () => cvPipelineFeature.runPipeline("full"));

        if (els.restartServerBtn) {
            els.restartServerBtn.addEventListener(
                "click",
                appOperationsFeature.restartServerFromWeb,
            );
        }

        if (els.runResearchBtn) {
            els.runResearchBtn.addEventListener("click", () =>
                researchFeature.onResearchPrimaryAction(),
            );
        }
        if (els.formatResearchBtn) {
            els.formatResearchBtn.addEventListener("click", () =>
                researchFeature.formatResearchPdf(),
            );
        }
        if (els.resetResearchPromptBtn) {
            els.resetResearchPromptBtn.addEventListener("click", () =>
                researchFeature.resetResearchPrompt(),
            );
        }
        if (els.copyResearchOutputBtn) {
            els.copyResearchOutputBtn.addEventListener("click", () =>
                researchFeature.copyResearchOutputToClipboard(),
            );
        }

        els.refreshLogsBtn.addEventListener("click", () => logsFeature.refreshLogs());
        els.logSelect.addEventListener("change", () => logsFeature.loadSelectedDebugLog());

        els.tabButtons.forEach((button) => {
            button.addEventListener("click", () =>
                uiLayoutFeature.setActiveTab(button.dataset.tab),
            );
        });
        els.cvTabButtons.forEach((button) => {
            button.addEventListener("click", () =>
                uiLayoutFeature.setActiveCvTab(button.dataset.cvTab),
            );
        });
        els.researchInputTabButtons.forEach((button) => {
            button.addEventListener("click", () =>
                uiLayoutFeature.setActiveResearchInputTab(button.dataset.researchInputTab),
            );
        });
        els.logTabButtons.forEach((button) => {
            button.addEventListener("click", () =>
                uiLayoutFeature.setActiveLogTab(button.dataset.logTab),
            );
        });
        els.researchOutputTabButtons.forEach((button) => {
            button.addEventListener("click", () =>
                uiLayoutFeature.setActiveResearchOutputTab(button.dataset.researchOutputTab),
            );
        });

        els.fileSaveButtons.forEach((button) => {
            button.addEventListener("click", () =>
                appOperationsFeature.saveSingleFile(button.dataset.file),
            );
        });
        els.fileLoadButtons.forEach((button) => {
            button.addEventListener("click", () =>
                appOperationsFeature.loadSingleFile(button.dataset.file),
            );
        });

        if (els.paneSplitter) {
            els.paneSplitter.addEventListener("pointerdown", uiLayoutFeature.onSplitterPointerDown);
            window.addEventListener("pointermove", uiLayoutFeature.onSplitterPointerMove);
            window.addEventListener("pointerup", uiLayoutFeature.onSplitterPointerUp);
            window.addEventListener("pointercancel", uiLayoutFeature.onSplitterPointerUp);
        }
        els.researchSplitters.forEach((splitter) => {
            splitter.addEventListener("pointerdown", uiLayoutFeature.onResearchSplitterPointerDown);
        });

        if (els.modelSelect) {
            els.modelSelect.addEventListener("change", () => {
                providerModelFeature.handleModelSelectChanged();
            });
        }
        if (els.providerSelect) {
            els.providerSelect.addEventListener("change", () => {
                providerModelFeature.handleProviderSelectChanged();
            });
        }
    }

    return {
        bindEventHandlers,
    };
}
