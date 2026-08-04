import { getStorageString, hasAnyStorageKeys, setStorageString } from "./storage-utils.js";

/**
 * Architecture role:
 * - Layer: frontend feature module consumed by app bootstrap.
 * - Responsibility: synchronize editable file content between DOM editors, localStorage draft state, and in-memory disk snapshots.
 *
 * Plain-language purpose:
 * - This module is the app's "draft and dirty-state manager".
 * - It tracks what users typed, mirrors shared editors between tabs, marks unsaved changes, and loads/saves browser drafts.
 */

/**
 * Dependencies required by draft/files feature.
 *
 * @typedef {Object} DraftFilesFeatureContext
 * @property {any} state Shared app state containing diskFiles map.
 * @property {any} els DOM element registry containing editors and label elements.
 * @property {any} editableFiles Editable file metadata map (tab label, title element, editor getter).
 * @property {any} localStorageKeys Local storage key map.
 * @property {(message: string, isError?: boolean) => void} setStatus App status renderer used by autosave.
 */

/**
 * Create draft/files feature.
 *
 * @param {DraftFilesFeatureContext} ctx Feature dependencies.
 * @returns {{currentFiles: () => any, syncDirtyIndicators: () => void, writeDraftToLocalStorage: () => void, hasLocalDraft: () => boolean, loadLocalDraft: (diskFiles?: any) => void, applyFilesToEditors: (files: any) => void, updateDiskSnapshot: (files: any) => void, bindMirroredEditors: (primaryEditor: HTMLTextAreaElement | null, mirrorEditor: HTMLTextAreaElement | null) => void, bindAutosave: () => void, syncResearchMirrorEditorsFromPrimary: () => void}}
 */
export function createDraftFilesFeature(ctx) {
    const { state, els, editableFiles, localStorageKeys, setStatus } = ctx;

    /**
     * Collect current editable file values from primary editors.
     * @returns {{cv: string, prompt: string, research_prompt: string, jobspec: string, env: string}}
     */
    function currentFiles() {
        return {
            cv: els.cvEditor.value,
            prompt: els.promptEditor.value,
            research_prompt: els.researchPromptEditor.value,
            jobspec: els.jobspecEditor.value,
            env: els.envEditor.value,
        };
    }

    /**
     * Update tab/title dirty markers based on disk snapshot deltas.
     * @returns {void}
     */
    function syncDirtyIndicators() {
        Object.entries(editableFiles).forEach(([key, cfg]) => {
            const editor = cfg.editor();
            const diskValue = state.diskFiles[key] || "";
            const isDirty = editor.value !== diskValue;
            const suffix = isDirty ? "*" : "";

            const tabLabelEls = els.tabLabels.filter((el) => el.dataset.labelFor === key);
            tabLabelEls.forEach((tabLabelEl) => {
                tabLabelEl.textContent = `${cfg.tabLabel}${suffix}`;
            });
            if (cfg.title) {
                cfg.title.textContent = `${cfg.tabLabel}${suffix}`;
            }
        });
    }

    /**
     * Keep research mirror editors in sync with their primary counterparts.
     * @returns {void}
     */
    function syncResearchMirrorEditorsFromPrimary() {
        if (els.researchJobspecEditor && els.jobspecEditor) {
            els.researchJobspecEditor.value = els.jobspecEditor.value;
        }
        if (els.researchCvEditor && els.cvEditor) {
            els.researchCvEditor.value = els.cvEditor.value;
        }
    }

    /**
     * Two-way bind mirrored editors so either side updates the other.
     * @param {HTMLTextAreaElement | null} primaryEditor Primary editor element.
     * @param {HTMLTextAreaElement | null} mirrorEditor Mirror editor element.
     * @returns {void}
     */
    function bindMirroredEditors(primaryEditor, mirrorEditor) {
        if (!primaryEditor || !mirrorEditor) {
            return;
        }

        let syncing = false;

        const syncValues = (source, target) => {
            if (syncing) {
                return;
            }
            if (target.value === source.value) {
                return;
            }

            syncing = true;
            target.value = source.value;
            target.dispatchEvent(new Event("input", { bubbles: true }));
            syncing = false;
        };

        primaryEditor.addEventListener("input", () => syncValues(primaryEditor, mirrorEditor));
        mirrorEditor.addEventListener("input", () => syncValues(mirrorEditor, primaryEditor));
    }

    /**
     * Persist current draft fields in localStorage.
     * @returns {void}
     */
    function writeDraftToLocalStorage() {
        const files = currentFiles();
        setStorageString(localStorageKeys.cv, files.cv);
        setStorageString(localStorageKeys.prompt, files.prompt);
        setStorageString(localStorageKeys.research_prompt, files.research_prompt);
        setStorageString(localStorageKeys.research_company, els.researchCompanyInput.value || "");
        setStorageString(localStorageKeys.research_urls, els.researchUrlsInput.value || "");
        setStorageString(localStorageKeys.jobspec, files.jobspec);
        setStorageString(localStorageKeys.env, files.env);
    }

    /**
     * Detect whether any local draft field exists.
     * @returns {boolean}
     */
    function hasLocalDraft() {
        return hasAnyStorageKeys([
            localStorageKeys.cv,
            localStorageKeys.prompt,
            localStorageKeys.research_prompt,
            localStorageKeys.research_company,
            localStorageKeys.research_urls,
            localStorageKeys.jobspec,
            localStorageKeys.env,
        ]);
    }

    /**
     * Load persisted draft values into editors/inputs.
     * @param {any} [diskFiles={}] Current disk values used for env fallback behavior.
     * @returns {void}
     */
    function loadLocalDraft(diskFiles = {}) {
        const cv = getStorageString(localStorageKeys.cv);
        const prompt = getStorageString(localStorageKeys.prompt);
        const researchPrompt = getStorageString(localStorageKeys.research_prompt);
        const researchCompany = getStorageString(localStorageKeys.research_company);
        const researchUrls = getStorageString(localStorageKeys.research_urls);
        const jobspec = getStorageString(localStorageKeys.jobspec);
        const env = getStorageString(localStorageKeys.env);

        if (cv !== null) {
            els.cvEditor.value = cv;
        }
        if (prompt !== null) {
            els.promptEditor.value = prompt;
        }
        if (researchPrompt !== null) {
            els.researchPromptEditor.value = researchPrompt;
        }
        if (researchCompany !== null) {
            els.researchCompanyInput.value = researchCompany;
        }
        if (researchUrls !== null) {
            els.researchUrlsInput.value = researchUrls;
        }
        if (jobspec !== null) {
            els.jobspecEditor.value = jobspec;
        }
        if (env !== null) {
            const diskEnv = diskFiles.env || "";
            if (env === "" && diskEnv.trim() !== "") {
                els.envEditor.value = diskEnv;
            } else {
                els.envEditor.value = env;
            }
        }

        syncResearchMirrorEditorsFromPrimary();
    }

    /**
     * Apply server file payload to primary editors.
     * @param {any} files File payload.
     * @returns {void}
     */
    function applyFilesToEditors(files) {
        els.cvEditor.value = files.cv || "";
        els.promptEditor.value = files.prompt || "";
        els.researchPromptEditor.value = files.research_prompt || "";
        els.jobspecEditor.value = files.jobspec || "";
        els.envEditor.value = files.env || "";
        syncResearchMirrorEditorsFromPrimary();
    }

    /**
     * Update in-memory snapshot of on-disk files for dirty checking.
     * @param {any} files File payload.
     * @returns {void}
     */
    function updateDiskSnapshot(files) {
        state.diskFiles = {
            cv: files.cv || "",
            prompt: files.prompt || "",
            research_prompt: files.research_prompt || "",
            jobspec: files.jobspec || "",
            env: files.env || "",
        };
        syncDirtyIndicators();
    }

    /**
     * Bind autosave listeners for primary and mirrored editor inputs.
     * @returns {void}
     */
    function bindAutosave() {
        let timer = null;
        const schedule = () => {
            if (timer) {
                clearTimeout(timer);
            }
            timer = setTimeout(() => {
                writeDraftToLocalStorage();
                setStatus("Draft saved to browser storage.");
            }, 300);
        };

        [
            els.cvEditor,
            els.promptEditor,
            els.researchPromptEditor,
            els.jobspecEditor,
            els.researchJobspecEditor,
            els.researchCvEditor,
            els.envEditor,
        ].forEach((editor) => {
            if (!editor) {
                return;
            }
            editor.addEventListener("input", schedule);
            editor.addEventListener("input", syncDirtyIndicators);
        });

        [els.researchCompanyInput, els.researchUrlsInput].forEach((inputEl) => {
            if (!inputEl) {
                return;
            }
            inputEl.addEventListener("input", schedule);
        });
    }

    return {
        currentFiles,
        syncDirtyIndicators,
        writeDraftToLocalStorage,
        hasLocalDraft,
        loadLocalDraft,
        applyFilesToEditors,
        updateDiskSnapshot,
        bindMirroredEditors,
        bindAutosave,
        syncResearchMirrorEditorsFromPrimary,
    };
}
