import { formatPreviewDateTime } from "./app-utils.js";

// Shown before the CV preview title when the CV was generated with a steering note.
const STEERING_INDICATOR = "🧭";

const PREVIEW_CONFIG = {
    cv: {
        label: "CV",
        fileName: "tailored_dev.pdf",
        payloadToSteering: (payload) =>
            payload && payload.outputs && typeof payload.outputs.steering === "string"
                ? payload.outputs.steering.trim()
                : "",
        payloadToExists: (payload) =>
            Boolean(payload && payload.outputs && payload.outputs.pdfExists),
        payloadToMtime: (payload) =>
            payload && payload.outputs && Number.isFinite(payload.outputs.pdfMtime)
                ? payload.outputs.pdfMtime
                : null,
        payloadToSourceGeneratedAt: (payload) => {
            const sourceMtime =
                payload && payload.outputs && Number.isFinite(payload.outputs.modelOutputMtime)
                    ? payload.outputs.modelOutputMtime * 1000
                    : null;
            if (sourceMtime !== null) {
                return sourceMtime;
            }

            const fallback =
                payload && payload.lastRun && typeof payload.lastRun.finishedAt === "string"
                    ? payload.lastRun.finishedAt
                    : null;
            return fallback;
        },
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
        payloadToSourceGeneratedAt: (payload) => {
            const fallback =
                payload && payload.lastRun && typeof payload.lastRun.finishedAt === "string"
                    ? payload.lastRun.finishedAt
                    : null;

            const rawJson =
                payload && payload.output && typeof payload.output.json === "string"
                    ? payload.output.json
                    : "";
            if (!rawJson.trim()) {
                return fallback;
            }

            try {
                const parsed = JSON.parse(rawJson);
                if (parsed && typeof parsed.generatedAt === "string") {
                    return parsed.generatedAt;
                }
            } catch {
                // Keep fallback when research JSON is unavailable or malformed.
            }

            return fallback;
        },
    },
};

/**
 * Architecture role:
 * - Layer: shared presentation feature used by app bootstrap.
 * - Responsibility: render preview state for generated CV and Research PDFs using one common behavior.
 *
 * Plain-language purpose:
 * - This module is the "PDF screen controller". It decides which PDF to show, whether it exists, and how title/link/iframe should look.
 */

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
        cv: { exists: false, mtime: null, sourceGeneratedAt: null, steering: "" },
        research: { exists: false, mtime: null, sourceGeneratedAt: null, steering: "" },
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

        return formatPreviewDateTime(mtimeSeconds * 1000, "-");
    }

    /**
     * Format source generation timestamp for preview title text.
     * @param {string | null | undefined} value ISO-like timestamp from model output metadata.
     * @returns {string} Formatted timestamp or "-".
     */
    function formatSourceGeneratedForPreview(value) {
        return formatPreviewDateTime(value, "-");
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
        previewState[kind].sourceGeneratedAt = cfg.payloadToSourceGeneratedAt(payload);
        previewState[kind].steering = cfg.payloadToSteering ? cfg.payloadToSteering(payload) : "";
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
            const sourceGeneratedText = formatSourceGeneratedForPreview(state.sourceGeneratedAt);
            const steeringPrefix = state.steering ? `${STEERING_INDICATOR} ` : "";
            els.pdfPreviewTitle.textContent =
                `${steeringPrefix}PDF Preview (${cfg.label}, Generated: ${generatedText}, ` +
                `Source generated: ${sourceGeneratedText})`;
            els.pdfPreviewTitle.title = state.steering ? `Steered: ${state.steering}` : "";
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
            els.pdfPlaceholder.textContent = "No document available";
        }
    }

    return {
        applyCvOutputState,
        applyResearchOutputState,
        updatePreview,
    };
}
