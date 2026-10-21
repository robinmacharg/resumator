import { getStorageString, setStorageString } from "./storage-utils.js";

/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap.
 * - Responsibility: populate the PDF theme selector, persist the choice, and re-run formatting when it changes.
 *
 * Plain-language purpose:
 * - The theme list comes from the server (themes/*.typ), so new preset files appear without UI changes.
 */

/**
 * Dependencies required by the theme feature.
 *
 * @typedef {Object} ThemeFeatureContext
 * @property {{selectedTheme: string, isRunning: boolean}} state Shared app state subset.
 * @property {{themeSelect?: HTMLSelectElement | null}} els DOM element registry subset.
 * @property {{selected_theme: string}} localStorageKeys Storage key for the theme selection.
 * @property {(kind: "full" | "format") => Promise<void>} runPipeline CV pipeline runner.
 * @property {(theme: string) => boolean} [onThemeChanged] Role-mode handler; returns true when it took the change
 *   (saved on the role, preview re-rendered), so there is no localStorage write or format run.
 */

/**
 * Create the theme feature.
 *
 * @param {ThemeFeatureContext} ctx Feature dependencies.
 * @returns {{populateThemeSelect: (themes: string[] | null | undefined) => void, applyTheme: (theme: string) => void, handleThemeSelectChanged: () => Promise<void>}} Public API.
 */
export function createThemeFeature(ctx) {
    const { state, els, localStorageKeys, runPipeline, onThemeChanged } = ctx;
    const DEFAULT_THEME = "default";

    /**
     * Turn a theme file name into a display label ("compact" -> "Compact").
     * @param {string} name
     * @returns {string}
     */
    function themeLabel(name) {
        return name.charAt(0).toUpperCase() + name.slice(1);
    }

    /**
     * Fill the selector from the server's theme list and restore the saved choice.
     * A saved theme that no longer exists falls back to the default.
     * @param {string[] | null | undefined} themes
     * @returns {void}
     */
    function populateThemeSelect(themes) {
        const names = Array.isArray(themes) && themes.length ? themes : [DEFAULT_THEME];
        const saved = (getStorageString(localStorageKeys.selected_theme, "") || "").trim();
        state.selectedTheme = names.includes(saved) ? saved : names[0];

        if (!els.themeSelect) {
            return;
        }
        els.themeSelect.innerHTML = "";
        names.forEach((name) => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = themeLabel(name);
            els.themeSelect.appendChild(opt);
        });
        els.themeSelect.value = state.selectedTheme;
    }

    /**
     * Show a role's theme (role mode). An unknown theme falls back to the default; nothing is persisted.
     * @param {string} theme
     * @returns {void}
     */
    function applyTheme(theme) {
        const names = els.themeSelect ? Array.from(els.themeSelect.options, (opt) => opt.value) : [];
        state.selectedTheme = names.includes(theme) ? theme : DEFAULT_THEME;
        if (els.themeSelect) {
            els.themeSelect.value = state.selectedTheme;
        }
    }

    /**
     * Persist the new theme and re-run formatting only (no model call).
     * @returns {Promise<void>}
     */
    async function handleThemeSelectChanged() {
        if (!els.themeSelect) {
            return;
        }
        state.selectedTheme = els.themeSelect.value || DEFAULT_THEME;
        if (onThemeChanged && onThemeChanged(state.selectedTheme)) {
            return;
        }
        setStorageString(localStorageKeys.selected_theme, state.selectedTheme);
        if (!state.isRunning) {
            await runPipeline("format");
        }
    }

    return {
        populateThemeSelect,
        applyTheme,
        handleThemeSelectChanged,
    };
}
