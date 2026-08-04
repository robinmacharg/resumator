/**
 * Architecture role:
 * - Layer: orchestration feature used by app bootstrap.
 * - Responsibility: run file-level operations, full reloads, tailored-output refresh, and server restart flow.
 *
 * Plain-language purpose:
 * - This module is the app's "operations runner".
 * - It handles button-driven tasks that talk to the backend and then updates editor/preview state consistently.
 */

/**
 * Dependencies required by app operations feature.
 *
 * @typedef {Object} AppOperationsFeatureContext
 * @property {any} els DOM element registry.
 * @property {any} editableFiles Editable file metadata map.
 * @property {(path: string, options?: RequestInit) => Promise<any>} api JSON API helper.
 * @property {(path: string) => Promise<string>} fetchText Text fetch helper.
 * @property {(ms: number) => Promise<void>} sleep Delay helper.
 * @property {() => any} currentFiles Current editable file payload.
 * @property {() => void} writeDraftToLocalStorage Draft persistence callback.
 * @property {(files: any) => void} updateDiskSnapshot Disk snapshot updater.
 * @property {(files: any) => void} applyFilesToEditors Apply file payload to primary editors.
 * @property {(payload: any) => void} applyCvOutputState Preview CV state updater.
 * @property {() => void} updatePreview Preview re-render callback.
 * @property {(running: boolean) => void} setRunning Running-state toggle callback.
 * @property {(message: string, isError?: boolean) => void} setStatus Status renderer.
 */

/**
 * Create app operations feature.
 *
 * @param {AppOperationsFeatureContext} ctx Feature dependencies.
 * @returns {{refreshTailoredOutput: () => Promise<void>, saveSingleFile: (fileKey: string) => Promise<void>, loadSingleFile: (fileKey: string) => Promise<void>, saveToDisk: () => Promise<void>, reloadFromDisk: () => Promise<void>, restartServerFromWeb: () => Promise<void>}}
 */
export function createAppOperationsFeature(ctx) {
    const {
        els,
        editableFiles,
        api,
        fetchText,
        sleep,
        currentFiles,
        writeDraftToLocalStorage,
        updateDiskSnapshot,
        applyFilesToEditors,
        applyCvOutputState,
        updatePreview,
        setRunning,
        setStatus,
    } = ctx;

    /**
     * Refresh tailored markdown output viewer from generated file.
     * @returns {Promise<void>}
     */
    async function refreshTailoredOutput() {
        if (!els.tailoredViewer) {
            return;
        }

        try {
            const text = await fetchText(`/output/tailored.md?ts=${Date.now()}`);
            els.tailoredViewer.value = text;
        } catch (_err) {
            els.tailoredViewer.value =
                "output/tailored.md not found yet. Run full pipeline first.";
        }
    }

    /**
     * Save a single editable file to disk.
     * @param {string} fileKey Editable file key.
     * @returns {Promise<void>}
     */
    async function saveSingleFile(fileKey) {
        if (!editableFiles[fileKey]) {
            return;
        }

        const payload = { files: { [fileKey]: currentFiles()[fileKey] } };
        setRunning(true);
        setStatus(`Saving ${editableFiles[fileKey].tabLabel}...`);
        try {
            writeDraftToLocalStorage();
            const result = await api("/api/save", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            const files = (result.state && result.state.files) || {};
            if (Object.keys(files).length > 0) {
                updateDiskSnapshot(files);
                applyFilesToEditors(files);
            }
            setStatus(`${editableFiles[fileKey].tabLabel} saved.`);
        } catch (err) {
            setStatus(`Save failed: ${err.message}`, true);
        } finally {
            setRunning(false);
        }
    }

    /**
     * Reload a single editable file from disk.
     * @param {string} fileKey Editable file key.
     * @returns {Promise<void>}
     */
    async function loadSingleFile(fileKey) {
        if (!editableFiles[fileKey]) {
            return;
        }

        setRunning(true);
        setStatus(`Loading ${editableFiles[fileKey].tabLabel} from disk...`);
        try {
            const result = await api("/api/state");
            const files = result.files || {};
            const editor = editableFiles[fileKey].editor();
            editor.value = files[fileKey] || "";
            writeDraftToLocalStorage();
            updateDiskSnapshot(files);
            setStatus(`${editableFiles[fileKey].tabLabel} loaded from disk.`);
        } catch (err) {
            setStatus(`Load failed: ${err.message}`, true);
        } finally {
            setRunning(false);
        }
    }

    /**
     * Save all editable files to disk.
     * @returns {Promise<void>}
     */
    async function saveToDisk() {
        setRunning(true);
        setStatus("Saving files...");
        try {
            writeDraftToLocalStorage();
            await api("/api/save", {
                method: "POST",
                body: JSON.stringify({ files: currentFiles() }),
            });
            setStatus("Saved to disk.");
        } catch (err) {
            setStatus(`Save failed: ${err.message}`, true);
        } finally {
            setRunning(false);
        }
    }

    /**
     * Reload all editable files from disk and refresh related UI outputs.
     * @returns {Promise<void>}
     */
    async function reloadFromDisk() {
        setRunning(true);
        setStatus("Reloading from disk...");

        try {
            const payload = await api("/api/state");
            applyFilesToEditors(payload.files || {});
            updateDiskSnapshot(payload.files || {});
            applyCvOutputState(payload);
            writeDraftToLocalStorage();
            updatePreview();
            await refreshTailoredOutput();
            setStatus("Reloaded from disk.");
        } catch (err) {
            setStatus(`Reload failed: ${err.message}`, true);
        } finally {
            setRunning(false);
        }
    }

    /**
     * Request backend restart and wait for API responsiveness before reloading page.
     * @returns {Promise<void>}
     */
    async function restartServerFromWeb() {
        const confirmed = window.confirm("Restart the CV web server now?");
        if (!confirmed) {
            return;
        }

        if (els.restartServerBtn) {
            els.restartServerBtn.disabled = true;
        }
        setStatus("Restart requested. Waiting for server...");

        try {
            await api("/api/server/restart", {
                method: "POST",
                body: JSON.stringify({}),
            });
        } catch (_err) {
            // If the server restarts quickly, request may abort. Continue to polling.
        }

        const start = Date.now();
        const maxWaitMs = 20_000;
        while (Date.now() - start < maxWaitMs) {
            try {
                await api("/api/state");
                window.location.reload();
                return;
            } catch (_err) {
                await sleep(600);
            }
        }

        if (els.restartServerBtn) {
            els.restartServerBtn.disabled = false;
        }
        setStatus("Server restart timed out. Refresh the page manually.", true);
    }

    return {
        refreshTailoredOutput,
        saveSingleFile,
        loadSingleFile,
        saveToDisk,
        reloadFromDisk,
        restartServerFromWeb,
    };
}
