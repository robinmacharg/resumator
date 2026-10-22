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
 * @property {any} [themeFeature] PDF theme feature API.
 * @property {any} [steeringFeature] Steering feature API.
 * @property {any} [roleWorkspaceFeature] Role sidebar, CV source and role controls.
 * @property {any} [roleRunsFeature] Role run-history picker.
 * @property {any} [roleMergeFeature] Promote/pull/import merge view.
 * @property {any} [cvHistoryFeature] CV version history dialog.
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
        themeFeature,
        steeringFeature,
        roleWorkspaceFeature,
        roleRunsFeature,
        roleMergeFeature,
        cvHistoryFeature,
    } = ctx;

    /**
     * Add a click listener when the element exists.
     * @param {HTMLElement | null | undefined} element
     * @param {() => void} handler
     * @returns {void}
     */
    function bindOptionalClick(element, handler) {
        if (!element) {
            return;
        }
        element.addEventListener("click", handler);
    }

    /**
     * Bind tab-style button groups where data-* drives selected value.
     * @param {Array<any>} buttons
     * @param {(button: any) => any} getValue
     * @param {(value: any) => void} onSelect
     * @returns {void}
     */
    function bindButtonGroup(buttons, getValue, onSelect) {
        buttons.forEach((button) => {
            button.addEventListener("click", () => onSelect(getValue(button)));
        });
    }

    /**
     * Attach event handlers for all interactive controls.
     * @returns {void}
     */
    function bindEventHandlers() {
        els.runFormatBtn.addEventListener("click", () => cvPipelineFeature.runPipeline("format"));
        els.runFullBtn.addEventListener("click", () => cvPipelineFeature.runPipeline("full"));

        bindOptionalClick(els.restartServerBtn, appOperationsFeature.restartServerFromWeb);

        bindOptionalClick(els.runResearchBtn, () => researchFeature.onResearchPrimaryAction());
        bindOptionalClick(els.formatResearchBtn, () => researchFeature.formatResearchPdf());
        bindOptionalClick(els.resetResearchPromptBtn, () => researchFeature.resetResearchPrompt());
        bindOptionalClick(els.copyResearchOutputBtn, () =>
            researchFeature.copyResearchOutputToClipboard(),
        );

        els.refreshLogsBtn.addEventListener("click", () => logsFeature.refreshLogs());
        els.logSelect.addEventListener("change", () => logsFeature.loadSelectedDebugLog());

        bindButtonGroup(
            els.tabButtons,
            (button) => button.dataset.tab,
            uiLayoutFeature.setActiveTab,
        );
        bindButtonGroup(
            els.cvTabButtons,
            (button) => button.dataset.cvTab,
            uiLayoutFeature.setActiveCvTab,
        );
        bindButtonGroup(
            els.researchInputTabButtons,
            (button) => button.dataset.researchInputTab,
            uiLayoutFeature.setActiveResearchInputTab,
        );
        bindButtonGroup(
            els.logTabButtons,
            (button) => button.dataset.logTab,
            uiLayoutFeature.setActiveLogTab,
        );
        bindButtonGroup(
            els.researchOutputTabButtons,
            (button) => button.dataset.researchOutputTab,
            uiLayoutFeature.setActiveResearchOutputTab,
        );

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
        if (els.roleSplitter) {
            els.roleSplitter.addEventListener("pointerdown", uiLayoutFeature.onRoleSplitterPointerDown);
        }
        els.researchSplitters.forEach((splitter) => {
            splitter.addEventListener("pointerdown", uiLayoutFeature.onResearchSplitterPointerDown);
        });

        if (els.modelSelect) {
            els.modelSelect.addEventListener(
                "change",
                providerModelFeature.handleModelSelectChanged,
            );
        }
        if (els.providerSelect) {
            els.providerSelect.addEventListener(
                "change",
                providerModelFeature.handleProviderSelectChanged,
            );
        }
        if (els.themeSelect && themeFeature) {
            els.themeSelect.addEventListener("change", themeFeature.handleThemeSelectChanged);
        }
        if (steeringFeature) {
            if (els.steeringEditor) {
                els.steeringEditor.addEventListener("input", steeringFeature.handleSteeringInput);
            }
            if (els.steerCheckbox) {
                els.steerCheckbox.addEventListener("change", steeringFeature.handleSteerCheckboxChanged);
            }
        }
        if (roleWorkspaceFeature) {
            bindOptionalClick(els.newRoleBtn, roleWorkspaceFeature.openNewRoleDialog);
            bindOptionalClick(els.deleteRoleBtn, roleWorkspaceFeature.deleteActiveRole);
            bindOptionalClick(els.newRoleCancelBtn, () => els.newRoleDialog.close());
            if (els.newRoleForm) {
                els.newRoleForm.addEventListener("submit", (event) => {
                    event.preventDefault();
                    roleWorkspaceFeature.createRoleFromDialog();
                });
            }
            if (els.roleStatusSelect) {
                els.roleStatusSelect.addEventListener("change", roleWorkspaceFeature.handleStatusChanged);
            }
            bindOptionalClick(els.roleTitleBtn, roleWorkspaceFeature.startRename);
            if (els.roleNameInput) {
                els.roleNameInput.addEventListener("blur", roleWorkspaceFeature.commitRename);
                els.roleNameInput.addEventListener("keydown", roleWorkspaceFeature.handleRenameKeydown);
            }
            if (els.cvSourceSelect) {
                els.cvSourceSelect.addEventListener("change", roleWorkspaceFeature.handleCvSourceChanged);
            }
            bindOptionalClick(els.firstRunExampleBtn, () => roleWorkspaceFeature.chooseFirstRun("example"));
            bindOptionalClick(els.firstRunBlankBtn, () => roleWorkspaceFeature.chooseFirstRun("blank"));
            if (els.firstRunDialog) {
                // Escape would leave a new install with no choice made; Chrome doesn't always let it be cancelled.
                els.firstRunDialog.addEventListener("cancel", (event) => event.preventDefault());
                els.firstRunDialog.addEventListener("close", roleWorkspaceFeature.handleFirstRunDialogClosed);
            }
        }
        if (roleMergeFeature) {
            bindOptionalClick(els.promoteCvBtn, () => roleMergeFeature.openMerge("promote"));
            bindOptionalClick(els.pullCvBtn, () => roleMergeFeature.openMerge("pull"));
            bindOptionalClick(els.importCvBtn, () => roleMergeFeature.openMerge("import"));
            bindOptionalClick(els.mergeApplyBtn, roleMergeFeature.applyMerge);
            bindOptionalClick(els.mergeCancelBtn, roleMergeFeature.closeMerge);
            if (els.mergeDialog) {
                els.mergeDialog.addEventListener("close", roleMergeFeature.closeMerge);
            }
        }
        if (cvHistoryFeature) {
            bindOptionalClick(els.cvHistoryBtn, cvHistoryFeature.openHistory);
            bindOptionalClick(els.historyRestoreBtn, cvHistoryFeature.restoreSelected);
            bindOptionalClick(els.historyCloseBtn, cvHistoryFeature.closeHistory);
            if (els.historyDialog) {
                els.historyDialog.addEventListener("close", cvHistoryFeature.closeHistory);
            }
        }
        if (roleRunsFeature && els.runSelect) {
            els.runSelect.addEventListener("change", roleRunsFeature.handleRunSelectChanged);
        }
        if (els.researchRunSelect) {
            els.researchRunSelect.addEventListener("change", researchFeature.handleResearchRunSelectChanged);
        }
    }

    return {
        bindEventHandlers,
    };
}
