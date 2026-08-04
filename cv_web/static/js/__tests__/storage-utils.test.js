import test from "node:test";
import assert from "node:assert/strict";

import {
    getStorageJson,
    getStorageString,
    hasAnyStorageKeys,
    setStorageJson,
    setStorageString,
} from "../storage-utils.js";

function createLocalStorageMock() {
    const store = new Map();
    return {
        getItem(key) {
            return store.has(key) ? store.get(key) : null;
        },
        setItem(key, value) {
            store.set(key, String(value));
        },
        clear() {
            store.clear();
        },
    };
}

test("storage-utils string helpers set and get values", () => {
    global.localStorage = createLocalStorageMock();

    setStorageString("a", "1");
    assert.equal(getStorageString("a"), "1");
    assert.equal(getStorageString("missing", "fallback"), "fallback");
});

test("storage-utils JSON helpers parse and fallback safely", () => {
    global.localStorage = createLocalStorageMock();

    setStorageJson("obj", { x: 1 });
    assert.deepEqual(getStorageJson("obj", {}), { x: 1 });

    setStorageString("broken", "{not json}");
    assert.deepEqual(getStorageJson("broken", { safe: true }), { safe: true });
});

test("storage-utils hasAnyStorageKeys detects key presence", () => {
    global.localStorage = createLocalStorageMock();

    assert.equal(hasAnyStorageKeys(["x", "y"]), false);
    setStorageString("y", "yes");
    assert.equal(hasAnyStorageKeys(["x", "y"]), true);
});
