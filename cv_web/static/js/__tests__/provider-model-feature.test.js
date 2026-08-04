import test from "node:test";
import assert from "node:assert/strict";

import { createProviderModelFeature } from "../provider-model-feature.js";

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

function createSelectMock() {
    const select = {
        value: "",
        options: [],
        appendChild(node) {
            this.options.push(node);
            if (!this.value) {
                this.value = node.value;
            }
        },
    };

    Object.defineProperty(select, "innerHTML", {
        get() {
            return "";
        },
        set(_value) {
            this.options = [];
            this.value = "";
        },
    });

    return select;
}

function installDomMocks() {
    global.localStorage = createLocalStorageMock();
    global.document = {
        createElement(_tag) {
            return {
                value: "",
                textContent: "",
                disabled: false,
                title: "",
            };
        },
    };
}

test("provider/model populate restores saved enabled provider and model", () => {
    installDomMocks();

    const state = {
        defaultProvider: "gemini",
        selectedProvider: "",
        selectedModel: "",
        modelsByProvider: {},
    };
    const providerSelect = createSelectMock();
    const modelSelect = createSelectMock();
    const localStorageKeys = {
        selected_provider: "provider",
        selected_model: "model",
    };

    localStorage.setItem(localStorageKeys.selected_provider, "openai");
    localStorage.setItem(localStorageKeys.selected_model, "gpt-4.1-mini");

    const feature = createProviderModelFeature({
        state,
        els: { providerSelect, modelSelect },
        localStorageKeys,
    });

    feature.populateProviderAndModelSelect(
        {
            defaultProvider: "gemini",
            options: [
                { value: "gemini", label: "Gemini", enabled: true },
                { value: "openai", label: "OpenAI", enabled: true },
            ],
        },
        {
            byProvider: {
                gemini: ["gemini-2.5-pro"],
                openai: ["gpt-4.1", "gpt-4.1-mini"],
            },
        },
    );

    assert.equal(state.selectedProvider, "openai");
    assert.equal(state.selectedModel, "gpt-4.1-mini");
    assert.equal(providerSelect.value, "openai");
    assert.equal(modelSelect.value, "gpt-4.1-mini");
});

test("provider/model populate falls back when saved provider disabled", () => {
    installDomMocks();

    const state = {
        defaultProvider: "gemini",
        selectedProvider: "",
        selectedModel: "",
        modelsByProvider: {},
    };
    const providerSelect = createSelectMock();
    const modelSelect = createSelectMock();
    const localStorageKeys = {
        selected_provider: "provider",
        selected_model: "model",
    };

    localStorage.setItem(localStorageKeys.selected_provider, "openai");

    const feature = createProviderModelFeature({
        state,
        els: { providerSelect, modelSelect },
        localStorageKeys,
    });

    feature.populateProviderAndModelSelect(
        {
            defaultProvider: "gemini",
            options: [
                { value: "gemini", label: "Gemini", enabled: true },
                { value: "openai", label: "OpenAI", enabled: false },
            ],
        },
        {
            byProvider: {
                gemini: ["gemini-2.5-pro"],
                openai: ["gpt-4.1"],
            },
        },
    );

    assert.equal(state.selectedProvider, "gemini");
    assert.equal(providerSelect.value, "gemini");
});

test("provider/model provider change clears model selection", () => {
    installDomMocks();

    const state = {
        defaultProvider: "gemini",
        selectedProvider: "",
        selectedModel: "gpt-4.1",
        modelsByProvider: { gemini: ["gemini-2.5-pro"], openai: ["gpt-4.1"] },
    };
    const providerSelect = createSelectMock();
    const modelSelect = createSelectMock();
    const localStorageKeys = {
        selected_provider: "provider",
        selected_model: "model",
    };

    const feature = createProviderModelFeature({
        state,
        els: { providerSelect, modelSelect },
        localStorageKeys,
    });

    feature.populateProviderAndModelSelect(
        {
            defaultProvider: "gemini",
            options: [
                { value: "gemini", label: "Gemini", enabled: true },
                { value: "openai", label: "OpenAI", enabled: true },
            ],
        },
        {
            byProvider: {
                gemini: ["gemini-2.5-pro"],
                openai: ["gpt-4.1"],
            },
        },
    );

    providerSelect.value = "openai";
    feature.handleProviderSelectChanged();

    assert.equal(state.selectedProvider, "openai");
    assert.equal(state.selectedModel, "");
    assert.equal(localStorage.getItem(localStorageKeys.selected_provider), "openai");
    assert.equal(localStorage.getItem(localStorageKeys.selected_model), "");
});
