/**
 * Architecture role:
 * - Layer: shared infrastructure utility for frontend modules.
 * - Responsibility: provide small HTTP helpers with consistent error handling.
 *
 * Plain-language purpose:
 * - This file is the app's "network helper". It wraps fetch so feature modules can call APIs without repeating boilerplate.
 */

/**
 * Execute a JSON API request.
 * @param {string} path Relative API path.
 * @param {RequestInit} [options={}] Fetch options.
 * @returns {Promise<any>} Parsed JSON payload.
 */
export async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }

    return response.json();
}

/**
 * Execute a text fetch request.
 * @param {string} path Relative path.
 * @returns {Promise<string>} Response body as text.
 */
export async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }
    return response.text();
}
