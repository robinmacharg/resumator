import { getStorageString, setStorageString } from "./storage-utils.js";

/**
 * Architecture role:
 * - Layer: configuration feature used by app bootstrap.
 * - Responsibility: manage provider and model selectors, normalize backend option payloads, and persist user selection.
 *
 * Plain-language purpose:
 * - A provider/model feature controls which AI backend provider (for example Gemini) and which model variant the app sends into run/research requests.
 * - It is the "model selection manager" for the UI.
 */

/**
 * Dependencies required by provider/model feature.
 * Boundaries: this feature owns provider/model option rendering and persistence only.
 *
 * @typedef {Object} ProviderModelFeatureContext
 * @property {any} state Shared app state subset for provider/model defaults and options.
 * @property {any} els DOM element registry containing provider/model selects.
 * @property {{selected_provider: string, selected_model: string}} localStorageKeys Storage keys for provider/model selection.
 */

/**
 * Create provider/model feature.
 * Purpose: normalize provider/model payloads, render selects, and persist selection state.
 *
 * @param {ProviderModelFeatureContext} ctx Feature dependencies.
 * @returns {{populateProviderAndModelSelect: (providersPayload: any, modelsPayload: any) => void, handleProviderSelectChanged: () => void, handleModelSelectChanged: () => void}} Public API.
 */
export function createProviderModelFeature(ctx) {
    const { state, els, localStorageKeys } = ctx;

    /**
     * Read model selection from UI.
     * @returns {string}
     */
    function selectedModelFromUi() {
        if (!els.modelSelect) {
            return "";
        }
        return (els.modelSelect.value || "").trim();
    }

    /**
     * Read provider selection from UI with default fallback.
     * @returns {string}
     */
    function selectedProviderFromUi() {
        if (!els.providerSelect) {
            return state.defaultProvider || "gemini";
        }
        return (els.providerSelect.value || state.defaultProvider || "gemini").trim();
    }

    /**
     * Persist selected provider to state/localStorage/UI.
     * @param {string} provider
     * @returns {void}
     */
    function setSelectedProvider(provider) {
        const next = (provider || state.defaultProvider || "gemini").trim();
        state.selectedProvider = next;
        setStorageString(localStorageKeys.selected_provider, next);
        if (els.providerSelect && els.providerSelect.value !== next) {
            els.providerSelect.value = next;
        }
    }

    /**
     * Persist selected model to state/localStorage/UI.
     * @param {string} model
     * @returns {void}
     */
    function setSelectedModel(model) {
        const next = (model || "").trim();
        state.selectedModel = next;
        setStorageString(localStorageKeys.selected_model, next);
        if (els.modelSelect && els.modelSelect.value !== next) {
            els.modelSelect.value = next;
        }
    }

    /**
     * Resolve model options for currently selected provider.
     * @returns {string[]}
     */
    function getActiveModelOptions() {
        const options = state.modelsByProvider[state.selectedProvider];
        return Array.isArray(options) ? options : [];
    }

    /**
     * Rebuild model selector options using current provider and saved model preference.
     * @returns {void}
     */
    function refreshModelSelectOptions() {
        if (!els.modelSelect) {
            return;
        }

        const defaultOptionValue = "";
        const defaultOptionLabel = "Default order";
        const modelOptions = getActiveModelOptions();

        const deduped = [];
        const seen = new Set();
        modelOptions.forEach((item) => {
            const cleaned = item.trim();
            if (!cleaned || seen.has(cleaned)) {
                return;
            }
            seen.add(cleaned);
            deduped.push(cleaned);
        });

        els.modelSelect.innerHTML = "";

        const defaultOpt = document.createElement("option");
        defaultOpt.value = defaultOptionValue;
        defaultOpt.textContent = defaultOptionLabel;
        els.modelSelect.appendChild(defaultOpt);

        deduped.forEach((modelName) => {
            const opt = document.createElement("option");
            opt.value = modelName;
            opt.textContent = modelName;
            els.modelSelect.appendChild(opt);
        });

        const savedSelection = (getStorageString(localStorageKeys.selected_model, "") || "").trim();
        const currentSelection = (state.selectedModel || "").trim();
        const selectedCandidate = currentSelection || savedSelection;
        const selected = deduped.includes(selectedCandidate)
            ? selectedCandidate
            : defaultOptionValue;
        setSelectedModel(selected);
    }

    /**
     * Populate provider and model selectors from API payloads.
     * @param {any} providersPayload
     * @param {any} modelsPayload
     * @returns {void}
     */
    function populateProviderAndModelSelect(providersPayload, modelsPayload) {
        const defaultProvider =
            providersPayload && typeof providersPayload.defaultProvider === "string"
                ? providersPayload.defaultProvider.trim() || "gemini"
                : "gemini";
        state.defaultProvider = defaultProvider;

        const providerOptions =
            providersPayload && Array.isArray(providersPayload.options)
                ? providersPayload.options
                      .filter(
                          (item) =>
                              item &&
                              typeof item.value === "string" &&
                              typeof item.label === "string",
                      )
                      .map((item) => ({
                          value: item.value.trim(),
                          label: item.label.trim(),
                          enabled: item.enabled !== false,
                          disabledReason:
                              typeof item.disabledReason === "string"
                                  ? item.disabledReason.trim()
                                  : "",
                      }))
                      .filter((item) => item.value && item.label)
                : [{ value: "gemini", label: "Gemini", enabled: true, disabledReason: "" }];

        if (els.providerSelect) {
            els.providerSelect.innerHTML = "";
            providerOptions.forEach((item) => {
                const opt = document.createElement("option");
                opt.value = item.value;
                opt.textContent = item.enabled ? item.label : `${item.label} (disabled)`;
                opt.disabled = !item.enabled;
                if (!item.enabled && item.disabledReason) {
                    opt.title = item.disabledReason;
                }
                els.providerSelect.appendChild(opt);
            });
        }

        state.modelsByProvider =
            modelsPayload &&
            modelsPayload.byProvider &&
            typeof modelsPayload.byProvider === "object"
                ? Object.fromEntries(
                      Object.entries(modelsPayload.byProvider).map(([provider, models]) => {
                          const cleaned = Array.isArray(models)
                              ? models
                                    .filter((item) => typeof item === "string" && item.trim())
                                    .map((item) => item.trim())
                              : [];
                          return [provider, cleaned];
                      }),
                  )
                : {};

        const savedProvider = (
            getStorageString(localStorageKeys.selected_provider, "") || ""
        ).trim();
        const enabledProviders = providerOptions
            .filter((item) => item.enabled)
            .map((item) => item.value);
        const fallbackProviders = providerOptions.map((item) => item.value);
        const selectedProvider = enabledProviders.includes(savedProvider)
            ? savedProvider
            : enabledProviders.includes(defaultProvider)
              ? defaultProvider
              : enabledProviders[0] || fallbackProviders[0] || "gemini";
        setSelectedProvider(selectedProvider);
        refreshModelSelectOptions();
    }

    /**
     * Persist current model when user changes model select.
     * @returns {void}
     */
    function handleModelSelectChanged() {
        setSelectedModel(selectedModelFromUi());
    }

    /**
     * Handle provider changes and reset model selection into provider-specific options.
     * @returns {void}
     */
    function handleProviderSelectChanged() {
        setSelectedProvider(selectedProviderFromUi());
        setSelectedModel("");
        refreshModelSelectOptions();
    }

    return {
        populateProviderAndModelSelect,
        handleProviderSelectChanged,
        handleModelSelectChanged,
    };
}
