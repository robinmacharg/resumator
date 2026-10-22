import test from "node:test";
import assert from "node:assert/strict";

import {
    describeImportDiff,
    describeTest,
    diffFields,
    diffOtherRows,
    errorMessage,
    isEmptyDiff,
    splitGroups,
} from "../settings-model.js";

const settings = [
    { key: "OPENAI_API_KEY", secret: true, isSet: true, value: "sk-…1234" },
    { key: "OPENAI_MODEL", secret: false, isSet: true, value: "m1" },
    { key: "OPENAI_API_URL", secret: false, isSet: false, value: "" },
];

test("diffFields: untouched form is empty, blank secret means unchanged", () => {
    const diff = diffFields(settings, { OPENAI_API_KEY: "", OPENAI_MODEL: "m1", OPENAI_API_URL: "" });
    assert.deepEqual(diff, { set: {}, delete: [] });
    assert.equal(isEmptyDiff(diff), true);
});

test("diffFields: typed secret and edited value are set; blanked stored value is deleted", () => {
    const diff = diffFields(settings, { OPENAI_API_KEY: "sk-new", OPENAI_MODEL: "", OPENAI_API_URL: "http://x" });
    assert.deepEqual(diff, { set: { OPENAI_API_KEY: "sk-new", OPENAI_API_URL: "http://x" }, delete: ["OPENAI_MODEL"] });
});

test("diffFields: a blanked value that was never stored is not a delete; unknown keys are skipped", () => {
    assert.deepEqual(diffFields(settings, { OPENAI_API_URL: "" }), { set: {}, delete: [] });
    assert.deepEqual(diffFields(settings, { NOPE: "x" }), { set: {}, delete: [] });
});

test("diffOtherRows: unchanged masked rows are left alone; edits, adds, removals and bad names are found", () => {
    const stored = [
        { key: "A", value: "1" },
        { key: "B_TOKEN", value: "ab…wxyz" },
        { key: "C", value: "3" },
    ];
    const diff = diffOtherRows(stored, [
        { key: "A", value: "2" },
        { key: "B_TOKEN", value: "ab…wxyz" },
        { key: "NEW", value: "n" },
        { key: "bad-key", value: "x" },
        { key: "", value: "" },
    ]);
    assert.deepEqual(diff, { set: { A: "2", NEW: "n" }, delete: ["C"], invalid: ["bad-key"] });
});

test("describeImportDiff lists key names and counts, never values", () => {
    assert.equal(
        describeImportDiff({ added: ["A", "B"], changed: ["C"], unchanged: ["D"], removed: [] }),
        "2 added (A, B); 1 changed (C); 1 unchanged",
    );
    assert.equal(describeImportDiff({ added: [], changed: [], unchanged: [], removed: [] }), "Nothing to import.");
});

test("describeTest and errorMessage", () => {
    assert.equal(describeTest({ ok: true, message: "OK", elapsedSeconds: 1.234, model: "m" }), "OK (m, 1.2s)");
    assert.equal(describeTest({ ok: false, message: "bad key", elapsedSeconds: 0, model: "" }), "Failed: bad key");
    assert.equal(errorMessage(new Error('{"error":"nope"}')), "nope");
    assert.equal(errorMessage(new Error("plain")), "plain");
});

test("splitGroups separates global, providers and other", () => {
    const parts = splitGroups([{ id: "global" }, { id: "openai" }, { id: "gemini" }, { id: "other" }]);
    assert.equal(parts.global.id, "global");
    assert.deepEqual(parts.providers.map((g) => g.id), ["openai", "gemini"]);
    assert.equal(parts.other.id, "other");
    assert.equal(splitGroups([{ id: "global" }]).other, null);
});
