const SPLITTER_MIN_LEFT_PX = 360;
const SPLITTER_MIN_RIGHT_PX = 320;
const RESEARCH_SPLITTER_MIN_SECTION_PX = 140;

/**
 * Architecture role:
 * - Layer: interaction/presentation feature used by app bootstrap.
 * - Responsibility: tab switching, persistence of active panels, and splitter drag interactions.
 *
 * Plain-language purpose:
 * - This module is the "layout coordinator". It controls what panel is visible and how the user resizes major sections.
 */

/**
 * Dependencies required by UI layout feature.
 * Boundaries: this feature owns tab activation state and splitter interactions; data fetching is delegated.
 *
 * @typedef {Object} UiLayoutFeatureContext
 * @property {any} state Shared app state subset for active tabs and drag state.
 * @property {any} els DOM registry for tab buttons/panels and splitter elements.
 * @property {any} localStorageKeys Local storage key map.
 * @property {() => void} onLogsTabActivated Callback when logs top tab is activated.
 * @property {() => void} onPreviewUpdate Callback to refresh preview on top-tab changes.
 * @property {() => void} onTailoredTabActivated Callback when CV tailored tab is activated.
 * @property {() => void} onTabsChanged Callback for tab changes that should trigger extra UI sync.
 */

/**
 * Create UI layout feature.
 * Purpose: centralize tab state transitions, persistence, and splitter pointer behavior.
 *
 * @param {UiLayoutFeatureContext} ctx Feature dependencies.
 * @returns {{initializeResearchSectionRatios: () => void, setActiveTab: (tabName: string) => void, setActiveCvTab: (tabName: string) => void, setActiveResearchInputTab: (tabName: string) => void, setActiveLogTab: (tabName: string) => void, setActiveResearchOutputTab: (tabName: string) => void, onSplitterPointerDown: (event: PointerEvent) => void, onResearchSplitterPointerDown: (event: PointerEvent) => void, onSplitterPointerMove: (event: PointerEvent) => void, onSplitterPointerUp: (event: PointerEvent) => void}}
 */
export function createUiLayoutFeature(ctx) {
    const {
        state,
        els,
        localStorageKeys,
        onLogsTabActivated,
        onPreviewUpdate,
        onTailoredTabActivated,
        onTabsChanged,
    } = ctx;

    /**
     * Normalize three research section ratios into fractions summing to 1.
     * @param {any} ratios Candidate ratio list.
     * @returns {number[]} Normalized 3-length ratio array.
     */
    function normalizeResearchRatios(ratios) {
        if (!Array.isArray(ratios) || ratios.length !== 3) {
            return [1 / 3, 1 / 3, 1 / 3];
        }

        const cleaned = ratios.map((value) => {
            const parsed = Number(value);
            return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
        });
        const sum = cleaned.reduce((acc, value) => acc + value, 0);

        if (sum <= 0) {
            return [1 / 3, 1 / 3, 1 / 3];
        }

        return cleaned.map((value) => value / sum);
    }

    /**
     * Apply research section ratios to CSS variables.
     * @param {number[]} ratios Top/middle/bottom ratios.
     * @param {boolean} [persist=true] Persist ratios in localStorage.
     * @returns {void}
     */
    function applyResearchSectionRatios(ratios, persist = true) {
        const panel = els.tabPanels.research;
        if (!panel) {
            return;
        }

        const normalized = normalizeResearchRatios(ratios);
        state.researchSectionRatios = normalized;

        panel.style.setProperty("--research-top-size", `${(normalized[0] * 100).toFixed(4)}%`);
        panel.style.setProperty("--research-middle-size", `${(normalized[1] * 100).toFixed(4)}%`);
        panel.style.setProperty("--research-bottom-size", `${(normalized[2] * 100).toFixed(4)}%`);

        if (persist) {
            localStorage.setItem(
                localStorageKeys.research_section_ratios,
                JSON.stringify(normalized),
            );
        }
    }

    /**
     * Initialize research section ratios from localStorage or defaults.
     * @returns {void}
     */
    function initializeResearchSectionRatios() {
        const savedRaw = localStorage.getItem(localStorageKeys.research_section_ratios);
        if (!savedRaw) {
            applyResearchSectionRatios([1 / 3, 1 / 3, 1 / 3], false);
            return;
        }

        try {
            const parsed = JSON.parse(savedRaw);
            applyResearchSectionRatios(parsed, false);
        } catch (_err) {
            applyResearchSectionRatios([1 / 3, 1 / 3, 1 / 3], false);
        }
    }

    /**
     * Activate top-level tab and persist selection.
     * @param {string} tabName Target tab name.
     * @returns {void}
     */
    function setActiveTab(tabName) {
        if (!els.tabPanels[tabName]) {
            return;
        }

        state.activeTab = tabName;
        localStorage.setItem(localStorageKeys.active_tab, tabName);
        els.tabButtons.forEach((button) => {
            const isActive = button.dataset.tab === tabName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
        });

        Object.entries(els.tabPanels).forEach(([name, panel]) => {
            panel.classList.toggle("active", name === tabName);
        });

        if (tabName === "logs") {
            onLogsTabActivated();
        }

        onPreviewUpdate();
    }

    /**
     * Activate CV sub-tab and persist selection.
     * @param {string} tabName Target CV sub-tab.
     * @returns {void}
     */
    function setActiveCvTab(tabName) {
        if (!els.cvTabPanels[tabName]) {
            return;
        }

        state.activeCvTab = tabName;
        localStorage.setItem(localStorageKeys.active_cv_tab, tabName);

        els.cvTabButtons.forEach((button) => {
            const isActive = button.dataset.cvTab === tabName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
        });

        Object.entries(els.cvTabPanels).forEach(([name, panel]) => {
            panel.classList.toggle("active", name === tabName);
        });

        if (tabName === "tailored") {
            onTailoredTabActivated();
        }
    }

    /**
     * Activate research input sub-tab and persist selection.
     * @param {string} tabName Target research input tab.
     * @returns {void}
     */
    function setActiveResearchInputTab(tabName) {
        if (!els.researchInputPanels[tabName]) {
            return;
        }

        state.activeResearchInputTab = tabName;
        localStorage.setItem(localStorageKeys.active_research_input_tab, tabName);

        els.researchInputTabButtons.forEach((button) => {
            const isActive = button.dataset.researchInputTab === tabName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
        });

        Object.entries(els.researchInputPanels).forEach(([name, panel]) => {
            panel.classList.toggle("active", name === tabName);
        });
    }

    /**
     * Activate logs tab (run/debug) and persist selection.
     * @param {string} tabName Target logs tab.
     * @returns {void}
     */
    function setActiveLogTab(tabName) {
        if (!els.logPanels[tabName]) {
            return;
        }

        state.activeLogTab = tabName;
        localStorage.setItem(localStorageKeys.active_log_tab, tabName);
        els.logTabButtons.forEach((button) => {
            const isActive = button.dataset.logTab === tabName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
        });

        Object.entries(els.logPanels).forEach(([name, panel]) => {
            panel.classList.toggle("active", name === tabName);
        });

        onTabsChanged();
    }

    /**
     * Activate research output tab and persist selection.
     * @param {string} tabName Target research output tab.
     * @returns {void}
     */
    function setActiveResearchOutputTab(tabName) {
        if (!els.researchOutputPanels[tabName]) {
            return;
        }

        state.activeResearchOutputTab = tabName;
        localStorage.setItem(localStorageKeys.research_output_tab, tabName);

        els.researchOutputTabButtons.forEach((button) => {
            const isActive = button.dataset.researchOutputTab === tabName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
        });

        Object.entries(els.researchOutputPanels).forEach(([name, panel]) => {
            panel.classList.toggle("active", name === tabName);
        });

        onTabsChanged();
    }

    /**
     * Update main pane splitter position in response to pointer movement.
     * @param {number} clientX Pointer X coordinate.
     * @returns {void}
     */
    function updateSplitterPosition(clientX) {
        if (!els.layout) {
            return;
        }

        const rect = els.layout.getBoundingClientRect();
        const maxLeft = rect.width - SPLITTER_MIN_RIGHT_PX;
        const next = Math.min(Math.max(clientX - rect.left, SPLITTER_MIN_LEFT_PX), maxLeft);
        const pct = (next / rect.width) * 100;
        els.layout.style.setProperty("--left-pane-width", `${pct}%`);
    }

    /**
     * Start drag interaction for main horizontal pane splitter.
     * @param {PointerEvent} event Pointer event.
     * @returns {void}
     */
    function onSplitterPointerDown(event) {
        if (!els.paneSplitter || window.matchMedia("(max-width: 1100px)").matches) {
            return;
        }

        state.isDraggingSplitter = true;
        els.paneSplitter.classList.add("dragging");
        els.paneSplitter.setPointerCapture(event.pointerId);
        updateSplitterPosition(event.clientX);
    }

    /**
     * Start drag interaction for research vertical splitters.
     * @param {PointerEvent} event Pointer event.
     * @returns {void}
     */
    function onResearchSplitterPointerDown(event) {
        if (!els.tabPanels.research || window.matchMedia("(max-width: 1100px)").matches) {
            return;
        }

        const splitter = event.currentTarget;
        if (!splitter || !splitter.dataset || !splitter.dataset.researchSplitter) {
            return;
        }

        const panelRect = els.tabPanels.research.getBoundingClientRect();
        const splitterCount = 2;
        const splitterSize = 6;
        const availableHeight = Math.max(panelRect.height - splitterCount * splitterSize, 1);
        const currentHeights = state.researchSectionRatios.map((ratio) => ratio * availableHeight);

        state.isDraggingResearchSplitter = true;
        state.activeResearchSplitter = {
            key: splitter.dataset.researchSplitter,
            startY: event.clientY,
            startHeights: currentHeights,
            element: splitter,
        };

        splitter.classList.add("dragging");
        splitter.setPointerCapture(event.pointerId);
    }

    /**
     * Handle pointer move while dragging either main or research splitters.
     * @param {PointerEvent} event Pointer event.
     * @returns {void}
     */
    function onSplitterPointerMove(event) {
        if (!state.isDraggingSplitter) {
            if (!state.isDraggingResearchSplitter || !state.activeResearchSplitter) {
                return;
            }

            const drag = state.activeResearchSplitter;
            const nextHeights = [...drag.startHeights];
            const deltaY = event.clientY - drag.startY;
            const minSection = RESEARCH_SPLITTER_MIN_SECTION_PX;

            if (drag.key === "top") {
                nextHeights[0] += deltaY;
                nextHeights[1] -= deltaY;

                if (nextHeights[0] < minSection) {
                    nextHeights[1] -= minSection - nextHeights[0];
                    nextHeights[0] = minSection;
                }
                if (nextHeights[1] < minSection) {
                    nextHeights[0] -= minSection - nextHeights[1];
                    nextHeights[1] = minSection;
                }
            } else {
                nextHeights[1] += deltaY;
                nextHeights[2] -= deltaY;

                if (nextHeights[1] < minSection) {
                    nextHeights[2] -= minSection - nextHeights[1];
                    nextHeights[1] = minSection;
                }
                if (nextHeights[2] < minSection) {
                    nextHeights[1] -= minSection - nextHeights[2];
                    nextHeights[2] = minSection;
                }
            }

            const total = nextHeights.reduce((acc, value) => acc + value, 0);
            if (total > 0) {
                applyResearchSectionRatios(nextHeights.map((value) => value / total));
            }
            return;
        }
        updateSplitterPosition(event.clientX);
    }

    /**
     * End active splitter drag interactions and release pointer capture.
     * @param {PointerEvent} event Pointer event.
     * @returns {void}
     */
    function onSplitterPointerUp(event) {
        if (state.isDraggingResearchSplitter && state.activeResearchSplitter) {
            const drag = state.activeResearchSplitter;
            state.isDraggingResearchSplitter = false;
            state.activeResearchSplitter = null;
            if (drag.element) {
                drag.element.classList.remove("dragging");
                try {
                    drag.element.releasePointerCapture(event.pointerId);
                } catch (_err) {
                    // Ignore capture release errors when pointer is no longer active.
                }
            }
        }

        if (!state.isDraggingSplitter || !els.paneSplitter) {
            return;
        }

        state.isDraggingSplitter = false;
        els.paneSplitter.classList.remove("dragging");
        try {
            els.paneSplitter.releasePointerCapture(event.pointerId);
        } catch (_err) {
            // Ignore capture release errors when pointer is no longer active.
        }
    }

    return {
        initializeResearchSectionRatios,
        setActiveTab,
        setActiveCvTab,
        setActiveResearchInputTab,
        setActiveLogTab,
        setActiveResearchOutputTab,
        onSplitterPointerDown,
        onResearchSplitterPointerDown,
        onSplitterPointerMove,
        onSplitterPointerUp,
    };
}
