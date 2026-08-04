import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const APP_JS_PATH = path.resolve(process.cwd(), "app.js");

test("app composition keeps startup wiring order", () => {
    const source = fs.readFileSync(APP_JS_PATH, "utf8");

    const bindIndex = source.indexOf("appEventBindingsFeature.bindEventHandlers();");
    const startupIndex = source.indexOf("appStartupFeature.runStartupSequence();");

    assert.ok(bindIndex >= 0, "Expected event-bindings startup call in app.js");
    assert.ok(startupIndex >= 0, "Expected startup sequence call in app.js");
    assert.ok(bindIndex < startupIndex, "Expected event handlers to bind before startup run");
});

test("app composition uses shared preview bindings across features", () => {
    const source = fs.readFileSync(APP_JS_PATH, "utf8");

    assert.ok(
        source.includes("const previewBindings = {"),
        "Expected shared previewBindings object",
    );
    assert.ok(
        source.includes("applyCvOutputState: previewBindings.applyCvOutputState"),
        "Expected app features to use shared applyCvOutputState binding",
    );
    assert.ok(
        source.includes("updatePreview: previewBindings.updatePreview"),
        "Expected app features to use shared updatePreview binding",
    );
});
