const PREVIEW_CONFIG = {
    cv: {
        label: "CV",
        fileName: "tailored_dev.pdf",
        payloadToExists: (payload) =>
            Boolean(payload && payload.outputs && payload.outputs.pdfExists),
        payloadToMtime: (payload) =>
            payload && payload.outputs && Number.isFinite(payload.outputs.pdfMtime)
                ? payload.outputs.pdfMtime
                : null,
    },
    research: {
        label: "Research",
        fileName: "research_output.formatted.pdf",
        payloadToExists: (payload) =>
            Boolean(payload && payload.output && payload.output.formattedPdfExists),
        payloadToMtime: (payload) =>
            payload && payload.output && Number.isFinite(payload.output.formattedPdfMtime)
                ? payload.output.formattedPdfMtime
                : null,
    },
};

/**
 * Dependencies required by PDF preview feature.
 * Boundaries: this feature manages preview state/rendering for known output kinds, but does not fetch payloads.
 *
 * @typedef {Object} PdfPreviewFeatureContext
 * @property {any} els DOM element registry subset for preview title/link/placeholder/iframe.
 * @property {() => "cv" | "research" | string} getActivePreviewKind Returns currently active preview kind.
 */

/**
 * Create generic PDF preview feature.
 * Purpose: centralize CV/Research preview rendering with shared behavior.
 *
 * @param {PdfPreviewFeatureContext} ctx Feature dependencies.
 * @returns {{applyCvOutputState: (payload: any) => void, applyResearchOutputState: (payload: any) => void, updatePreview: () => void}} Public preview API.
 */
export function createPdfPreviewFeature(ctx) {
    const { els, getActivePreviewKind } = ctx;

    const previewState = {
        cv: { exists: false, mtime: null },
        research: { exists: false, mtime: null },
    };

    /**
     * Format unix mtime seconds into user-facing preview timestamp.
     * @param {number | null | undefined} mtimeSeconds Unix timestamp in seconds.
     * @returns {string} Formatted timestamp or "-".
     */
    function formatMtimeForPreview(mtimeSeconds) {
        if (
            typeof mtimeSeconds !== "number" ||
            !Number.isFinite(mtimeSeconds) ||
            mtimeSeconds <= 0
        ) {
            return "-";
        }

        const date = new Date(mtimeSeconds * 1000);
        if (Number.isNaN(date.getTime())) {
            return "-";
        }

        const pad2 = (n) => String(n).padStart(2, "0");
        const day = pad2(date.getDate());
        const month = pad2(date.getMonth() + 1);
        const year = date.getFullYear();
        const hours = pad2(date.getHours());
        const mins = pad2(date.getMinutes());
        const secs = pad2(date.getSeconds());
        return `${day}/${month}/${year} - ${hours}:${mins}:${secs}`;
    }

    /**
     * Apply API payload to internal preview state for a known kind.
     * @param {"cv" | "research"} kind Preview kind.
     * @param {any} payload Server payload containing output metadata.
     * @returns {void}
     */
    function applyPayload(kind, payload) {
        const cfg = PREVIEW_CONFIG[kind];
        if (!cfg) {
            return;
        }

        previewState[kind].exists = cfg.payloadToExists(payload);
        previewState[kind].mtime = cfg.payloadToMtime(payload);
    }

    /**
     * Update internal CV preview state from API payload.
     * @param {any} payload API payload.
     * @returns {void}
     */
    function applyCvOutputState(payload) {
        applyPayload("cv", payload);
    }

    /**
     * Update internal Research preview state from API payload.
     * @param {any} payload API payload.
     * @returns {void}
     */
    function applyResearchOutputState(payload) {
        applyPayload("research", payload);
    }

    /**
     * Render preview iframe/link/title based on active preview kind.
     * @returns {void}
     */
    function updatePreview() {
        const kind = getActivePreviewKind() === "research" ? "research" : "cv";
        const cfg = PREVIEW_CONFIG[kind];
        const state = previewState[kind];

        if (els.pdfPreviewTitle) {
            const generatedText = formatMtimeForPreview(state.mtime);
            els.pdfPreviewTitle.textContent = `PDF Preview (${cfg.label}, Generated: ${generatedText})`;
        }

        if (els.pdfPreviewOpenLink) {
            els.pdfPreviewOpenLink.href = `/output/${cfg.fileName}`;
            els.pdfPreviewOpenLink.style.pointerEvents = state.exists ? "auto" : "none";
            els.pdfPreviewOpenLink.style.opacity = state.exists ? "1" : "0.45";
        }

        if (state.exists) {
            const ts = Date.now();
            els.pdfPreview.classList.remove("hidden");
            if (els.pdfPlaceholder) {
                els.pdfPlaceholder.classList.remove("visible");
            }
            els.pdfPreview.src = `/output/${cfg.fileName}?ts=${ts}`;
            return;
        }

        els.pdfPreview.classList.add("hidden");
        if (els.pdfPlaceholder) {
            els.pdfPlaceholder.classList.add("visible");
            els.pdfPlaceholder.textContent = "No document availabel";
        }
    }

    return {
        applyCvOutputState,
        applyResearchOutputState,
        updatePreview,
    };
}
