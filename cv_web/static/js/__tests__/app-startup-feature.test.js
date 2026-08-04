import test from "node:test";
import assert from "node:assert/strict";

import { createAppStartupFeature } from "../app-startup-feature.js";

function createHarness() {
    const calls = [];

    const els = {
        jobspecEditor: { id: "jobspec" },
        researchJobspecEditor: { id: "researchJobspec" },
        cvEditor: { id: "cv" },
        researchCvEditor: { id: "researchCv" },
    };

    const feature = createAppStartupFeature({
        els,
        bindAutosave: () => {
            calls.push({ type: "bindAutosave" });
        },
        bindMirroredEditors: (primaryEditor, mirrorEditor) => {
            calls.push({
                type: "bindMirroredEditors",
                primary: primaryEditor ? primaryEditor.id : null,
                mirror: mirrorEditor ? mirrorEditor.id : null,
            });
        },
        uiLayoutFeature: {
            initializeResearchSectionRatios: () => {
                calls.push({ type: "initializeResearchSectionRatios" });
            },
        },
        syncResearchPrimaryButton: () => {
            calls.push({ type: "syncResearchPrimaryButton" });
        },
        initialize: () => {
            calls.push({ type: "initialize" });
            return Promise.resolve();
        },
    });

    return { feature, calls };
}

test("app-startup executes startup sequence in expected order", () => {
    const { feature, calls } = createHarness();

    feature.runStartupSequence();

    assert.deepEqual(
        calls.map((entry) => entry.type),
        [
            "bindAutosave",
            "bindMirroredEditors",
            "bindMirroredEditors",
            "initializeResearchSectionRatios",
            "syncResearchPrimaryButton",
            "initialize",
        ],
    );
});

test("app-startup binds the expected mirrored editor pairs", () => {
    const { feature, calls } = createHarness();

    feature.runStartupSequence();

    const mirroredCalls = calls.filter((entry) => entry.type === "bindMirroredEditors");
    assert.deepEqual(mirroredCalls, [
        {
            type: "bindMirroredEditors",
            primary: "jobspec",
            mirror: "researchJobspec",
        },
        {
            type: "bindMirroredEditors",
            primary: "cv",
            mirror: "researchCv",
        },
    ]);
});
