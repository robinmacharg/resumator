import { getStorageString, setStorageString } from "./storage-utils.js";

/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap.
 * - Responsibility: keep the Steering tab text and the "Steer CV generation" checkbox in localStorage,
 *   and build the steering part of full-run requests.
 *
 * Plain-language purpose:
 * - Steering is a free-text note that tells the agent what this CV should emphasise (plan D11).
 * - In file mode it lives in the browser only; the server receives it with each full run. In role mode it is kept
 *   on the role (`onSteeringChanged` handles the edits).
 */

/**
 * Dependencies required by the steering feature.
 *
 * @typedef {Object} SteeringFeatureContext
 * @property {{steeringEditor?: HTMLTextAreaElement | null, steerCheckbox?: HTMLInputElement | null}} els DOM element registry subset.
 * @property {{steering_text: string, steering_enabled: string}} localStorageKeys Storage keys for steering state.
 * @property {(steering: {text: string, enabled: boolean}) => boolean} [onSteeringChanged] Role-mode handler;
 *   returns true when it saved the change, so localStorage is left alone.
 */

/**
 * Create the steering feature.
 *
 * @param {SteeringFeatureContext} ctx Feature dependencies.
 * @returns {{restoreSteering: () => void, applySteering: (steering: {text: string, enabled: boolean}) => void, handleSteeringInput: () => void, handleSteerCheckboxChanged: () => void, getSteeringRequest: () => {enabled: boolean, text: string}}} Public API.
 */
export function createSteeringFeature(ctx) {
    const { els, localStorageKeys, onSteeringChanged } = ctx;

    /**
     * Pass the edit to the role-mode handler. True when it took it.
     * @returns {boolean}
     */
    function handledByRole() {
        if (!onSteeringChanged) {
            return false;
        }
        return onSteeringChanged({
            text: els.steeringEditor ? els.steeringEditor.value : "",
            enabled: els.steerCheckbox ? els.steerCheckbox.checked : true,
        });
    }

    /**
     * Restore the saved steering text and checkbox (checked by default).
     * @returns {void}
     */
    function restoreSteering() {
        if (els.steeringEditor) {
            els.steeringEditor.value = getStorageString(localStorageKeys.steering_text, "") || "";
        }
        if (els.steerCheckbox) {
            els.steerCheckbox.checked =
                getStorageString(localStorageKeys.steering_enabled, "true") !== "false";
        }
    }

    /**
     * Show a role's steering (role mode); nothing is written to localStorage.
     * @param {{text: string, enabled: boolean}} steering
     * @returns {void}
     */
    function applySteering(steering) {
        if (els.steeringEditor) {
            els.steeringEditor.value = steering.text || "";
        }
        if (els.steerCheckbox) {
            els.steerCheckbox.checked = Boolean(steering.enabled);
        }
    }

    /**
     * Persist the steering text as the user types.
     * @returns {void}
     */
    function handleSteeringInput() {
        if (handledByRole()) {
            return;
        }
        if (els.steeringEditor) {
            setStorageString(localStorageKeys.steering_text, els.steeringEditor.value);
        }
    }

    /**
     * Persist the checkbox state.
     * @returns {void}
     */
    function handleSteerCheckboxChanged() {
        if (handledByRole()) {
            return;
        }
        if (els.steerCheckbox) {
            setStorageString(localStorageKeys.steering_enabled, String(els.steerCheckbox.checked));
        }
    }

    /**
     * Steering for a full-run request. Disabled sends no text, so the agent gets no steering section.
     * @returns {{enabled: boolean, text: string}}
     */
    function getSteeringRequest() {
        const enabled = els.steerCheckbox ? els.steerCheckbox.checked : true;
        const text = els.steeringEditor ? els.steeringEditor.value.trim() : "";
        return { enabled, text: enabled ? text : "" };
    }

    return {
        restoreSteering,
        applySteering,
        handleSteeringInput,
        handleSteerCheckboxChanged,
        getSteeringRequest,
    };
}
