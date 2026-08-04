export function createLogsFeature(ctx) {
    const {
        els,
        api,
        setRunLogOutput,
        summarizeRun,
        setDebugLogOutput,
    } = ctx;

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
