/**
 * Architecture role:
 * - Layer: composition support feature used by app bootstrap.
 * - Responsibility: execute the final startup sequence after all features are constructed.
 *
 * Plain-language purpose:
 * - This module is the app's "startup launcher".
 * - It runs one-time setup steps (autosave wiring, mirrored editors, layout ratio init, initial button sync, and async initialize call).
 */

/**
 * Dependencies required by app startup feature.
 *
 * @typedef {Object} AppStartupFeatureContext
 * @property {any} els DOM element registry.
 * @property {() => void} bindAutosave Draft autosave binding callback.
 * @property {(primaryEditor: HTMLTextAreaElement | null, mirrorEditor: HTMLTextAreaElement | null) => void} bindMirroredEditors Mirrored editor binding callback.
 * @property {{initializeResearchSectionRatios: () => void, initializeRoleSidebarWidth: () => void}} uiLayoutFeature Layout feature API subset.
 * @property {() => void} syncResearchPrimaryButton Run-state button sync callback.
 * @property {() => Promise<void>} initialize App initialization callback.
 */

/**
 * Create app startup feature.
 *
 * @param {AppStartupFeatureContext} ctx Feature dependencies.
 * @returns {{runStartupSequence: () => void}}
 */
export function createAppStartupFeature(ctx) {
    const {
        els,
        bindAutosave,
        bindMirroredEditors,
        uiLayoutFeature,
        syncResearchPrimaryButton,
        initialize,
    } = ctx;

    /**
     * Bind all mirrored editor pairs used in startup.
     * @returns {void}
     */
    function bindMirroredEditorPairs() {
        [
            [els.jobspecEditor, els.researchJobspecEditor],
            [els.cvEditor, els.researchCvEditor],
        ].forEach(([primaryEditor, mirrorEditor]) => {
            bindMirroredEditors(primaryEditor, mirrorEditor);
        });
    }

    /**
     * Execute startup sequence once after all features are composed.
     * @returns {void}
     */
    function runStartupSequence() {
        bindAutosave();
        bindMirroredEditorPairs();
        uiLayoutFeature.initializeResearchSectionRatios();
        uiLayoutFeature.initializeRoleSidebarWidth();
        syncResearchPrimaryButton();
        initialize();
    }

    return {
        runStartupSequence,
    };
}
