/**
 * Architecture role:
 * - Layer: pure helpers for the Settings panel (no DOM).
 * - Responsibility: turn form values into the `{set, delete}` request body, and format diffs and test results.
 *
 * Plain-language purpose:
 * - Keeps the "what changed?" rules testable. Secrets show blank in the form (the server only ever sends a masked
 *   placeholder), so a blank secret means "leave as is" and typing replaces it.
 */

const KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * Value a field starts with in the form: secrets start blank, everything else shows its stored value.
 * @param {{secret: boolean, value: string}} setting
 * @returns {string}
 */
export function initialValue(setting) {
    return setting.secret ? "" : setting.value || "";
}

/**
 * Compare form values with the stored settings of one group.
 * Secrets: blank = unchanged. Others: same as stored = unchanged, blank = remove the key (use the default).
 *
 * @param {Array<{key: string, secret: boolean, isSet: boolean, value: string}>} settings
 * @param {Record<string, string>} values Current form values by key.
 * @returns {{set: Record<string, string>, delete: string[]}}
 */
export function diffFields(settings, values) {
    const diff = { set: {}, delete: [] };
    for (const setting of settings) {
        if (!(setting.key in values)) {
            continue;
        }
        const value = values[setting.key];
        if (value === initialValue(setting)) {
            continue;
        }
        if (value === "") {
            if (setting.isSet) {
                diff.delete.push(setting.key);
            }
        } else {
            diff.set[setting.key] = value;
        }
    }
    return diff;
}

/**
 * Compare the "Other" key/value rows with the stored undeclared keys.
 * A row whose value is still the masked placeholder is unchanged; a deleted or renamed row removes its key.
 *
 * @param {Array<{key: string, value: string}>} settings Stored undeclared settings (values may be masked).
 * @param {Array<{key: string, value: string}>} rows Rows in the editor.
 * @returns {{set: Record<string, string>, delete: string[], invalid: string[]}}
 */
export function diffOtherRows(settings, rows) {
    const stored = new Map(settings.map((setting) => [setting.key, setting.value]));
    const diff = { set: {}, delete: [], invalid: [] };
    const kept = new Set();
    for (const row of rows) {
        const key = row.key.trim();
        if (!key && !row.value) {
            continue;
        }
        if (!KEY_RE.test(key)) {
            diff.invalid.push(key);
            continue;
        }
        kept.add(key);
        if (!stored.has(key) || stored.get(key) !== row.value) {
            if (row.value !== "") {
                diff.set[key] = row.value;
            }
        }
    }
    for (const key of stored.keys()) {
        if (!kept.has(key)) {
            diff.delete.push(key);
        }
    }
    return diff;
}

/**
 * @param {{set: Record<string, string>, delete: string[]}} diff
 * @returns {boolean}
 */
export function isEmptyDiff(diff) {
    return Object.keys(diff.set).length === 0 && diff.delete.length === 0;
}

/**
 * One-line summary of an import diff (key names only, never values).
 * @param {{added: string[], changed: string[], unchanged: string[], removed: string[]}} diff
 * @returns {string}
 */
export function describeImportDiff(diff) {
    const parts = [];
    for (const label of ["added", "changed", "removed"]) {
        const keys = diff[label] || [];
        if (keys.length) {
            parts.push(`${keys.length} ${label} (${keys.join(", ")})`);
        }
    }
    const unchanged = (diff.unchanged || []).length;
    if (unchanged) {
        parts.push(`${unchanged} unchanged`);
    }
    return parts.length ? parts.join("; ") : "Nothing to import.";
}

/**
 * @param {{ok: boolean, message: string, elapsedSeconds: number, model: string}} result
 * @returns {string}
 */
export function describeTest(result) {
    const detail = result.model ? ` (${result.model}, ${Number(result.elapsedSeconds || 0).toFixed(1)}s)` : "";
    return result.ok ? `OK${detail}` : `Failed${detail}: ${result.message}`;
}

/**
 * Pull the message out of an api-client error (its text is the server's JSON body).
 * @param {unknown} error
 * @returns {string}
 */
export function errorMessage(error) {
    const text = error instanceof Error ? error.message : String(error);
    try {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed.error === "string") {
            return parsed.error;
        }
    } catch {
        // not JSON: use the text as is
    }
    return text;
}

/**
 * Split the API groups into the three kinds of block the panel shows.
 * @param {Array<{id: string, settings: any[]}>} groups
 * @returns {{global: any | null, providers: any[], other: any | null}}
 */
export function splitGroups(groups) {
    return {
        global: groups.find((group) => group.id === "global") || null,
        providers: groups.filter((group) => group.id !== "global" && group.id !== "other"),
        other: groups.find((group) => group.id === "other") || null,
    };
}
