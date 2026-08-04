/**
 * Architecture role:
 * - Layer: shared persistence helpers.
 * - Responsibility: provide safe and consistent localStorage access patterns.
 *
 * Plain-language purpose:
 * - This module centralizes localStorage read/write/default behavior so features do not duplicate storage boilerplate.
 */

/**
 * Get a string value from localStorage.
 * @param {string} key
 * @param {string | null} [fallback=null]
 * @returns {string | null}
 */
export function getStorageString(key, fallback = null) {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
}

/**
 * Set a string value in localStorage.
 * @param {string} key
 * @param {string} value
 * @returns {void}
 */
export function setStorageString(key, value) {
    localStorage.setItem(key, value);
}

/**
 * Get a JSON value from localStorage with parse fallback.
 * @template T
 * @param {string} key
 * @param {T} fallback
 * @returns {T}
 */
export function getStorageJson(key, fallback) {
    const raw = localStorage.getItem(key);
    if (!raw) {
        return fallback;
    }
    try {
        return JSON.parse(raw);
    } catch (_err) {
        return fallback;
    }
}

/**
 * Set a JSON value in localStorage.
 * @param {string} key
 * @param {any} value
 * @returns {void}
 */
export function setStorageJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

/**
 * Check whether any provided key is present in localStorage.
 * @param {string[]} keys
 * @returns {boolean}
 */
export function hasAnyStorageKeys(keys) {
    return keys.some((key) => localStorage.getItem(key) !== null);
}
