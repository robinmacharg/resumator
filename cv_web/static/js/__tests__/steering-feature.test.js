import test from "node:test";
import assert from "node:assert/strict";

import { createSteeringFeature } from "../steering-feature.js";

const localStorageKeys = {
    steering_text: "cvweb.steering_text",
    steering_enabled: "cvweb.steering_enabled",
};

function createLocalStorageMock() {
    const store = new Map();
    return {
        getItem(key) {
            return store.has(key) ? store.get(key) : null;
        },
        setItem(key, value) {
            store.set(key, String(value));
        },
    };
}

function createHarness() {
    global.localStorage = createLocalStorageMock();
    const els = {
        steeringEditor: { value: "" },
        steerCheckbox: { checked: false },
    };
    return { els, feature: createSteeringFeature({ els, localStorageKeys }) };
}

test("steering restore defaults to an empty note with steering enabled", () => {
    const { els, feature } = createHarness();

    feature.restoreSteering();

    assert.equal(els.steeringEditor.value, "");
    assert.equal(els.steerCheckbox.checked, true);
});

test("steering restore brings back the saved note and checkbox", () => {
    const { els, feature } = createHarness();
    localStorage.setItem(localStorageKeys.steering_text, "AI focus");
    localStorage.setItem(localStorageKeys.steering_enabled, "false");

    feature.restoreSteering();

    assert.equal(els.steeringEditor.value, "AI focus");
    assert.equal(els.steerCheckbox.checked, false);
});

test("steering input and checkbox changes are persisted", () => {
    const { els, feature } = createHarness();

    els.steeringEditor.value = "multi-domain skills";
    feature.handleSteeringInput();
    els.steerCheckbox.checked = false;
    feature.handleSteerCheckboxChanged();

    assert.equal(localStorage.getItem(localStorageKeys.steering_text), "multi-domain skills");
    assert.equal(localStorage.getItem(localStorageKeys.steering_enabled), "false");
});

test("steering request sends trimmed text only when enabled", () => {
    const { els, feature } = createHarness();
    els.steeringEditor.value = "  AI focus  ";

    els.steerCheckbox.checked = true;
    assert.deepEqual(feature.getSteeringRequest(), { enabled: true, text: "AI focus" });

    els.steerCheckbox.checked = false;
    assert.deepEqual(feature.getSteeringRequest(), { enabled: false, text: "" });
});

test("steering edits go to the role-mode handler instead of localStorage when it takes them", () => {
    global.localStorage = createLocalStorageMock();
    const seen = [];
    let roleMode = true;
    const els = { steeringEditor: { value: "" }, steerCheckbox: { checked: true } };
    const feature = createSteeringFeature({
        els,
        localStorageKeys,
        onSteeringChanged: (steering) => {
            seen.push(steering);
            return roleMode;
        },
    });

    feature.applySteering({ text: "role note", enabled: false });
    assert.equal(els.steeringEditor.value, "role note");
    assert.equal(els.steerCheckbox.checked, false);

    feature.handleSteeringInput();
    assert.deepEqual(seen, [{ text: "role note", enabled: false }]);
    assert.equal(localStorage.getItem(localStorageKeys.steering_text), null);

    roleMode = false;
    feature.handleSteeringInput();
    assert.equal(localStorage.getItem(localStorageKeys.steering_text), "role note");
});
