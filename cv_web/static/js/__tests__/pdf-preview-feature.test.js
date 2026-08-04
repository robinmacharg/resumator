import test from "node:test";
import assert from "node:assert/strict";

import { createPdfPreviewFeature } from "../pdf-preview-feature.js";

function createClassList() {
    const values = new Set();
    return {
        add(name) {
            values.add(name);
        },
        remove(name) {
            values.delete(name);
        },
        has(name) {
            return values.has(name);
        },
    };
}

function createEls() {
    return {
        pdfPreview: {
            classList: createClassList(),
            src: "",
        },
        pdfPlaceholder: {
            classList: createClassList(),
            textContent: "",
        },
        pdfPreviewTitle: {
            textContent: "",
        },
        pdfPreviewOpenLink: {
            href: "",
            style: {
                pointerEvents: "",
                opacity: "",
            },
        },
    };
}

test("pdf preview renders CV output when file exists", () => {
    const els = createEls();
    let activeKind = "cv";

    const originalNow = Date.now;
    Date.now = () => 12345;

    try {
        const feature = createPdfPreviewFeature({
            els,
            getActivePreviewKind: () => activeKind,
        });

        feature.applyCvOutputState({
            outputs: {
                pdfExists: true,
                pdfMtime: 1,
            },
        });
        feature.updatePreview();

        assert.equal(els.pdfPreview.classList.has("hidden"), false);
        assert.equal(els.pdfPlaceholder.classList.has("visible"), false);
        assert.equal(els.pdfPreview.src, "/output/tailored_dev.pdf?ts=12345");
        assert.equal(els.pdfPreviewOpenLink.href, "/output/tailored_dev.pdf");
        assert.equal(els.pdfPreviewOpenLink.style.pointerEvents, "auto");
        assert.equal(els.pdfPreviewOpenLink.style.opacity, "1");
        assert.equal(els.pdfPreviewTitle.textContent.includes("PDF Preview (CV, Generated:"), true);
        assert.equal(els.pdfPreviewTitle.textContent.includes("Generated: -"), false);
    } finally {
        Date.now = originalNow;
    }
});

test("pdf preview renders placeholder when research PDF is missing", () => {
    const els = createEls();

    const feature = createPdfPreviewFeature({
        els,
        getActivePreviewKind: () => "research",
    });

    feature.applyResearchOutputState({
        output: {
            formattedPdfExists: false,
            formattedPdfMtime: null,
        },
    });
    feature.updatePreview();

    assert.equal(els.pdfPreview.classList.has("hidden"), true);
    assert.equal(els.pdfPlaceholder.classList.has("visible"), true);
    assert.equal(els.pdfPlaceholder.textContent, "No document available");
    assert.equal(els.pdfPreviewOpenLink.href, "/output/research_output.formatted.pdf");
    assert.equal(els.pdfPreviewOpenLink.style.pointerEvents, "none");
    assert.equal(els.pdfPreviewOpenLink.style.opacity, "0.45");
    assert.equal(els.pdfPreviewTitle.textContent, "PDF Preview (Research, Generated: -)");
});

test("pdf preview defaults to CV when active kind is unknown", () => {
    const els = createEls();

    const feature = createPdfPreviewFeature({
        els,
        getActivePreviewKind: () => "other",
    });

    feature.updatePreview();

    assert.equal(els.pdfPreviewTitle.textContent, "PDF Preview (CV, Generated: -)");
    assert.equal(els.pdfPreviewOpenLink.href, "/output/tailored_dev.pdf");
});

test("pdf preview reads research payload metadata when available", () => {
    const els = createEls();
    const originalNow = Date.now;
    Date.now = () => 333;

    try {
        const feature = createPdfPreviewFeature({
            els,
            getActivePreviewKind: () => "research",
        });

        feature.applyResearchOutputState({
            output: {
                formattedPdfExists: true,
                formattedPdfMtime: 1700000000,
            },
        });
        feature.updatePreview();

        assert.equal(els.pdfPreview.src, "/output/research_output.formatted.pdf?ts=333");
        assert.equal(
            els.pdfPreviewTitle.textContent.startsWith("PDF Preview (Research, Generated: "),
            true,
        );
        assert.equal(els.pdfPreviewOpenLink.style.pointerEvents, "auto");
    } finally {
        Date.now = originalNow;
    }
});

test("pdf preview tolerates malformed payloads and keeps safe defaults", () => {
    const els = createEls();

    const feature = createPdfPreviewFeature({
        els,
        getActivePreviewKind: () => "research",
    });

    feature.applyCvOutputState(null);
    feature.applyResearchOutputState({
        output: { formattedPdfExists: 0, formattedPdfMtime: "bad" },
    });
    feature.updatePreview();

    assert.equal(els.pdfPreview.classList.has("hidden"), true);
    assert.equal(els.pdfPlaceholder.classList.has("visible"), true);
    assert.equal(els.pdfPlaceholder.textContent, "No document available");
    assert.equal(els.pdfPreviewOpenLink.href, "/output/research_output.formatted.pdf");
    assert.equal(els.pdfPreviewOpenLink.style.pointerEvents, "none");
    assert.equal(els.pdfPreviewOpenLink.style.opacity, "0.45");
    assert.equal(els.pdfPreviewTitle.textContent, "PDF Preview (Research, Generated: -)");
});
