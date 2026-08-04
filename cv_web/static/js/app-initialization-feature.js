/**
 * Architecture role:
 * - Layer: orchestration feature used by app bootstrap.
 * - Responsibility: load startup state, hydrate UI from APIs/localStorage, and restore tab/layout selections.
 *
 * Plain-language purpose:
 * - This module is the app's "startup coordinator".
 * - It performs the initial data load and restores the screen to the last usable state when the page opens.
 */

/**
 * Dependencies required by app initialization feature.
 *
 * @typedef {Object} AppInitializationFeatureContext
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API helper.
 * @property {any} els DOM element registry.
 * @property {any} localStorageKeys Local storage key map.
 * @property {any} providerModelFeature Provider/model feature API.
 * @property {any} uiLayoutFeature UI layout feature API.
 * @property {any} researchFeature Research feature API.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 * @property {(files: any) => void} applyFilesToEditors Apply files to editors.
 * @property {(files: any) => void} updateDiskSnapshot Update disk snapshot.
 * @property {(payload: any) => void} applyCvOutputState Update CV preview state.
 * @property {(payload: any) => void} renderResearchState Render research state.
 * @property {() => boolean} hasLocalDraft Whether browser draft exists.
 * @property {(diskFiles?: any) => void} loadLocalDraft Load browser draft.
 * @property {() => void} writeDraftToLocalStorage Persist current draft.
 * @property {() => void} syncDirtyIndicators Update dirty markers.
 * @property {(text: string) => void} setRunLogOutput Run output renderer.
 * @property {(run: any) => string} summarizeRun Run summary formatter.
 * @property {(run: any) => string} summarizeResearchOutput Research summary formatter.
 * @property {(text: string) => void} setResearchOutput Research output renderer.
 * @property {(command: any) => void} setResearchCommandOutput Research command renderer.
 * @property {(message: string, isError?: boolean) => void} setResearchStatus Research status renderer.
 * @property {(running: boolean) => void} setResearchRunning Research running-state setter.
 * @property {() => void} updatePreview Refresh preview rendering.
 * @property {() => Promise<void>} refreshTailoredOutput Refresh tailored markdown output.
 */

/**
 * Create app initialization feature.
 *
 * @param {AppInitializationFeatureContext} ctx Feature dependencies.
 * @returns {{initialize: () => Promise<void>}}
 */
export function createAppInitializationFeature(ctx) {
    const {
        api,
        els,
        localStorageKeys,
        providerModelFeature,
        uiLayoutFeature,
        researchFeature,
        setStatus,
        applyFilesToEditors,
        updateDiskSnapshot,
        applyCvOutputState,
        renderResearchState,
        hasLocalDraft,
        loadLocalDraft,
        writeDraftToLocalStorage,
        syncDirtyIndicators,
        setRunLogOutput,
        summarizeRun,
        summarizeResearchOutput,
        setResearchOutput,
        setResearchCommandOutput,
        setResearchStatus,
        setResearchRunning,
        updatePreview,
        refreshTailoredOutput,
    } = ctx;

    /**
     * Restore active tabs from localStorage, falling back to defaults.
     * @returns {void}
     */
    function restoreSavedTabs() {
        const savedTab = localStorage.getItem(localStorageKeys.active_tab);
        if (savedTab && els.tabPanels[savedTab]) {
            uiLayoutFeature.setActiveTab(savedTab);
        } else {
            uiLayoutFeature.setActiveTab("cv");
        }

        const savedCvTab = localStorage.getItem(localStorageKeys.active_cv_tab);
        if (savedCvTab && els.cvTabPanels[savedCvTab]) {
            uiLayoutFeature.setActiveCvTab(savedCvTab);
        } else {
            uiLayoutFeature.setActiveCvTab("cv");
        }

        const savedResearchInputTab = localStorage.getItem(localStorageKeys.active_research_input_tab);
        if (savedResearchInputTab && els.researchInputPanels[savedResearchInputTab]) {
            uiLayoutFeature.setActiveResearchInputTab(savedResearchInputTab);
        } else {
            uiLayoutFeature.setActiveResearchInputTab("query");
        }

        const savedLogTab = localStorage.getItem(localStorageKeys.active_log_tab);
        if (savedLogTab && els.logPanels[savedLogTab]) {
            uiLayoutFeature.setActiveLogTab(savedLogTab);
        } else {
            uiLayoutFeature.setActiveLogTab("run");
        }

        const savedResearchOutputTab = localStorage.getItem(localStorageKeys.research_output_tab);
        if (savedResearchOutputTab && els.researchOutputPanels[savedResearchOutputTab]) {
            uiLayoutFeature.setActiveResearchOutputTab(savedResearchOutputTab);
        } else {
            uiLayoutFeature.setActiveResearchOutputTab("console");
        }
    }

    /**
     * Restore UI/output state for an in-progress or completed research run.
     * @returns {Promise<void>}
     */
    async function restoreResearchRuntimeState() {
        const currentResearch = await researchFeature.fetchResearchStatus();
        if (currentResearch.run) {
            setResearchOutput(summarizeResearchOutput(currentResearch.run));
            setResearchCommandOutput(currentResearch.run.command || []);
            if (currentResearch.running) {
                setResearchStatus("Research run in progress...");
                setResearchRunning(true);
                researchFeature
                    .waitForResearchCompletion()
                    .then((run) => {
                        setResearchCommandOutput((run && run.command) || []);
                        if (run && run.success) {
                            setResearchStatus(`Research complete (${run.elapsedSeconds}s).`);
                        } else {
                            setResearchStatus("Research run failed.", true);
                        }
                    })
                    .catch((err) => {
                        setResearchStatus(`Research status polling failed: ${err.message}`, true);
                    })
                    .finally(() => {
                        setResearchRunning(false);
                    });
            } else {
                setResearchStatus(currentResearch.run.success ? "Last run succeeded." : "Last run failed.");
            }
        } else {
            setResearchStatus("Idle.");
            setResearchCommandOutput([]);
        }
    }

    /**
     * Initialize app state, tabs, providers/models, logs, and research state.
     * @returns {Promise<void>}
     */
    async function initialize() {
        setStatus("Loading editor state...");
        try {
            const payload = await api("/api/state");
            providerModelFeature.populateProviderAndModelSelect(
                payload.providers || null,
                payload.models || null,
            );
            applyFilesToEditors(payload.files || {});
            updateDiskSnapshot(payload.files || {});
            applyCvOutputState(payload);

            const researchPayload = await api("/api/research/state");
            renderResearchState(researchPayload);

            if (hasLocalDraft()) {
                loadLocalDraft(payload.files || {});
                setStatus("Loaded browser draft. Use per-tab Save to write to disk.");
                syncDirtyIndicators();
            } else {
                writeDraftToLocalStorage();
                setStatus("Loaded from disk.");
                syncDirtyIndicators();
            }

            if (payload.lastRun) {
                setRunLogOutput(summarizeRun(payload.lastRun));
            }

            await restoreResearchRuntimeState();

            updatePreview();
            await refreshTailoredOutput();
            restoreSavedTabs();
        } catch (err) {
            setStatus(`Initialization failed: ${err.message}`, true);
        }
    }

    return {
        initialize,
    };
}
