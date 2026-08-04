const SPLITTER_MIN_LEFT_PX = 360;
const SPLITTER_MIN_RIGHT_PX = 320;
const RESEARCH_SPLITTER_MIN_SECTION_PX = 140;

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

    function onSplitterPointerDown(event) {
        if (!els.paneSplitter || window.matchMedia("(max-width: 1100px)").matches) {
            return;
        }

        state.isDraggingSplitter = true;
        els.paneSplitter.classList.add("dragging");
        els.paneSplitter.setPointerCapture(event.pointerId);
        updateSplitterPosition(event.clientX);
    }

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
