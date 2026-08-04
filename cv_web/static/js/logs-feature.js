/**
 * Architecture role:
 * - Layer: support feature used by app bootstrap.
 * - Responsibility: load run/debug log metadata and selected debug log content.
 *
 * Plain-language purpose:
 * - This module is the "log viewer backend" for the UI. It populates log selectors and fetches log text on demand.
 */

/**
 * Dependencies required by logs feature.
 * Boundaries: this feature fetches log data and updates log UI controls; no global app state ownership.
 *
 * @typedef {Object} LogsFeatureContext
 * @property {any} els DOM element registry subset (log select and outputs).
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API request helper.
 * @property {(text: string) => void} setRunLogOutput Run log text renderer.
 * @property {(run: any) => string} summarizeRun Run formatter.
 * @property {(text: string) => void} setDebugLogOutput Debug log renderer.
 */

/**
 * Create logs feature.
 * Purpose: load log index, populate debug-log selector, and load selected debug log content.
 *
 * @param {LogsFeatureContext} ctx Feature dependencies.
 * @returns {{refreshLogs: () => Promise<void>, loadSelectedDebugLog: () => Promise<void>}} Public logs API.
 */
export function createLogsFeature(ctx) {
    const { els, api, setRunLogOutput, summarizeRun, setDebugLogOutput } = ctx;

    /**
     * Refresh log index and run summary output.
     * @returns {Promise<void>}
     */
    async function refreshLogs() {
        try {
            const payload = await api("/api/logs");
            const logs = payload.logs || [];

            els.logSelect.innerHTML = "";
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "Select debug log...";
            els.logSelect.appendChild(placeholder);

            logs.forEach((item) => {
                const option = document.createElement("option");
                option.value = item.name;
                const when = new Date(item.mtime * 1000).toLocaleString();
                option.textContent = `${item.name} (${when})`;
                els.logSelect.appendChild(option);
            });

            if (payload.lastRun) {
                setRunLogOutput(summarizeRun(payload.lastRun));
            }
        } catch (err) {
            setDebugLogOutput(`Unable to load logs: ${err.message}`);
        }
    }

    /**
     * Load content for selected debug log file.
     * @returns {Promise<void>}
     */
    async function loadSelectedDebugLog() {
        const name = els.logSelect.value;
        if (!name) {
            setDebugLogOutput("Select a debug log to view its content.");
            return;
        }

        try {
            const payload = await api(`/api/logs/content?name=${encodeURIComponent(name)}`);
            setDebugLogOutput(payload.content || "(Empty log file)");
        } catch (err) {
            setDebugLogOutput(`Unable to load log file: ${err.message}`);
        }
    }

    return {
        refreshLogs,
        loadSelectedDebugLog,
    };
}
