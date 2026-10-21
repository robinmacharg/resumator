import { getStorageString, setStorageString } from "./storage-utils.js";

/**
 * Architecture role:
 * - Layer: domain workflow feature used by app bootstrap.
 * - Responsibility: keep the Steering tab text and the "Steer CV generation" checkbox in localStorage,
 *   and build the steering part of full-run requests.
 *
 * Plain-language purpose:
 * - Steering is a free-text note that tells the agent what this CV should emphasise (plan D11).
 * - It lives in the browser only; the server receives it with each full run.
 */

/**
 * Dependencies required by the steering feature.
 *
 * @typedef {Object} SteeringFeatureContext
 * @property {{steeringEditor?: HTMLTextAreaElement | null, steerCheckbox?: HTMLInputElement | null}} els DOM element registry subset.
 * @property {{steering_text: string, steering_enabled: string}} localStorageKeys Storage keys for steering state.
 */

/**
 * Create the steering feature.
 *
 * @param {SteeringFeatureContext} ctx Feature dependencies.
 * @returns {{restoreSteering: () => void, handleSteeringInput: () => void, handleSteerCheckboxChanged: () => void, getSteeringRequest: () => {enabled: boolean, text: string}}} Public API.
 */
export function createSteeringFeature(ctx) {
    const { els, localStorageKeys } = ctx;

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
     * Persist the steering text as the user types.
     * @returns {void}
     */
    function handleSteeringInput() {
        if (els.steeringEditor) {
            setStorageString(localStorageKeys.steering_text, els.steeringEditor.value);
        }
    }

    /**
     * Persist the checkbox state.
     * @returns {void}
     */
    function handleSteerCheckboxChanged() {
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
        handleSteeringInput,
        handleSteerCheckboxChanged,
        getSteeringRequest,
    };
}
