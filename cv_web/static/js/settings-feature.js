import { api } from "./api-client.js";
import {
    describeImportDiff,
    describeTest,
    diffFields,
    diffOtherRows,
    errorMessage,
    initialValue,
    isEmptyDiff,
    splitGroups,
} from "./settings-model.js";

/**
 * Architecture role:
 * - Layer: domain feature for the Settings sub-tab (settings-in-db task 7).
 * - Responsibility: render the settings catalog (Global, provider cards, Other), save changes, reveal secrets,
 *   test providers, import `.env` text with a diff preview, and view the settings as `.env` text.
 *
 * Plain-language purpose:
 * - This is where keys and options live now that `.env` is gone. Everything goes through `/api/settings…`;
 *   secrets only appear in the page when the user presses Reveal.
 */

/**
 * @typedef {Object} SettingsFeatureContext
 * @property {any} els DOM registry subset: settingsBody, settingsStatus, settingsImportBtn, settingsSampleBtn,
 *   settingsEnvBtn, settingsImportPanel, settingsImportText, settingsImportFile, settingsImportMode,
 *   settingsImportPreviewBtn, settingsImportApplyBtn, settingsImportCloseBtn, settingsImportResult,
 *   settingsEnvPanel, settingsEnvText, settingsEnvRevealBtn, settingsEnvCopyBtn, settingsEnvDownloadBtn,
 *   settingsEnvCloseBtn.
 * @property {(path: string, options?: RequestInit) => Promise<any>} [apiClient] Test seam; defaults to `api`.
 * @property {Document} [doc] Test seam; defaults to `document`.
 * @property {() => void} [onSettingsChanged] Called after settings are saved or imported (refresh providers).
 */

/**
 * @param {SettingsFeatureContext} ctx
 * @returns {{bind: () => void, load: () => Promise<void>}}
 */
export function createSettingsFeature(ctx) {
    const { els } = ctx;
    const request = ctx.apiClient || api;
    const doc = ctx.doc || document;
    const onSettingsChanged = ctx.onSettingsChanged || (() => {});
    let groups = [];
    let envRevealed = false;

    /** @param {string} message @param {boolean} [isError] */
    function setStatus(message, isError = false) {
        if (els.settingsStatus) {
            els.settingsStatus.textContent = message;
            els.settingsStatus.classList.toggle("settings-error", isError);
        }
    }

    /**
     * @param {string} tag
     * @param {Record<string, any>} [props] className, textContent, type, value, title, placeholder, ...
     * @param {any[]} [children]
     */
    function h(tag, props = {}, children = []) {
        const element = doc.createElement(tag);
        for (const [name, value] of Object.entries(props)) {
            element[name] = value;
        }
        children.forEach((child) => element.appendChild(child));
        return element;
    }

    /** @param {string} path @param {string} method @param {any} body */
    function send(path, method, body) {
        return request(path, { method, body: JSON.stringify(body) });
    }

    // ---------------------------------------------------------------- fields

    /**
     * Build the input for one setting; returns `{row, read}` where `read()` is the current form value.
     * @param {any} setting
     */
    function buildField(setting) {
        const start = initialValue(setting);
        let input;
        if (setting.kind === "bool" || setting.kind === "choice") {
            const options = setting.kind === "bool" ? ["true", "false"] : setting.choices || [];
            const defaultLabel = setting.default ? `(default: ${setting.default})` : "(not set)";
            input = h("select", {}, [
                h("option", { value: "", textContent: defaultLabel }),
                ...options.map((option) => h("option", { value: option, textContent: option })),
            ]);
            input.value = start;
        } else {
            input = h("input", {
                type: setting.secret ? "password" : "text",
                value: start,
                placeholder: setting.secret
                    ? setting.isSet
                        ? `${setting.value} (set; type to replace)`
                        : "not set"
                    : setting.default || "",
                autocomplete: "off",
                spellcheck: false,
            });
        }
        input.id = `setting-${setting.key}`;
        const children = [
            h("label", { htmlFor: input.id, textContent: setting.label, title: setting.key }),
            input,
        ];
        if (setting.secret && setting.isSet) {
            const reveal = h("button", { type: "button", className: "btn btn-secondary", textContent: "Reveal" });
            reveal.addEventListener("click", async () => {
                try {
                    const result = await send("/api/settings/reveal", "POST", { key: setting.key });
                    input.type = "text";
                    input.value = result.value;
                } catch (error) {
                    setStatus(errorMessage(error), true);
                }
            });
            children.push(reveal);
        }
        const row = h("div", { className: "settings-field" }, children);
        if (setting.help) {
            row.appendChild(h("small", { className: "settings-help", textContent: setting.help }));
        }
        return { row, read: () => input.value };
    }

    /**
     * Fields for one group, with an Advanced section that starts collapsed.
     * @param {any} group
     * @returns {{element: any, collect: () => {set: Record<string,string>, delete: string[]}}}
     */
    function buildFieldList(group) {
        const reads = {};
        const container = h("div", { className: "settings-fields" });
        const advanced = h("details", { className: "settings-advanced" }, [
            h("summary", { textContent: "Advanced" }),
        ]);
        group.settings.forEach((setting) => {
            const field = buildField(setting);
            reads[setting.key] = field.read;
            (setting.advanced ? advanced : container).appendChild(field.row);
        });
        if (advanced.children.length > 1) {
            container.appendChild(advanced);
        }
        return {
            element: container,
            collect: () => {
                const values = {};
                Object.entries(reads).forEach(([key, read]) => {
                    values[key] = read();
                });
                return diffFields(group.settings, values);
            },
        };
    }

    // ---------------------------------------------------------------- saving

    /** @param {{set: Record<string,string>, delete: string[]}} diff @param {string} done */
    async function save(diff, done) {
        if (isEmptyDiff(diff)) {
            setStatus("Nothing to save.");
            return;
        }
        try {
            const result = await send("/api/settings", "PUT", diff);
            groups = result.groups;
            render();
            setStatus(done);
            onSettingsChanged();
        } catch (error) {
            setStatus(errorMessage(error), true);
        }
    }

    // ---------------------------------------------------------------- blocks

    function buildGlobal(group) {
        const fields = buildFieldList(group);
        const save_ = h("button", { type: "button", className: "btn btn-primary", textContent: "Save" });
        save_.addEventListener("click", () => save(fields.collect(), "Global settings saved."));
        return h("section", { className: "settings-block" }, [
            h("h3", { textContent: "Global" }),
            fields.element,
            h("div", { className: "settings-actions" }, [save_]),
        ]);
    }

    function buildProvider(group) {
        const enabled = Boolean(group.status && group.status.enabled);
        const fields = buildFieldList(group);
        const result = h("span", { className: "settings-test-result", role: "status" });
        const test = h("button", { type: "button", className: "btn btn-secondary", textContent: "Test" });
        const saveBtn = h("button", { type: "button", className: "btn btn-primary", textContent: "Save" });
        test.addEventListener("click", async () => {
            const diff = fields.collect();
            const overrides = { ...diff.set };
            diff.delete.forEach((key) => {
                overrides[key] = "";
            });
            result.textContent = "Testing (one real model call)…";
            test.disabled = true;
            try {
                const outcome = await send("/api/settings/test", "POST", { provider: group.id, overrides });
                result.textContent = describeTest(outcome);
                result.classList.toggle("settings-error", !outcome.ok);
            } catch (error) {
                result.textContent = errorMessage(error);
                result.classList.add("settings-error");
            } finally {
                test.disabled = false;
            }
        });
        saveBtn.addEventListener("click", () => save(fields.collect(), `${group.label} saved.`));
        const badge = h("span", {
            className: `settings-badge ${enabled ? "settings-badge-on" : "settings-badge-off"}`,
            textContent: enabled ? "enabled" : "not configured",
            title: group.status ? group.status.reason : "",
        });
        const summary = h("summary", {}, [h("strong", { textContent: group.label }), badge]);
        const card = h("details", { className: "settings-card" }, [
            summary,
            fields.element,
            h("div", { className: "settings-actions" }, [test, saveBtn, result]),
        ]);
        if (group.status && group.status.reason && !enabled) {
            fields.element.insertBefore(
                h("small", { className: "settings-help", textContent: group.status.reason }),
                fields.element.firstChild,
            );
        }
        card.open = enabled;
        return card;
    }

    function buildOther(group) {
        const settings = group ? group.settings : [];
        const rows = [];
        const list = h("div", { className: "settings-fields" });
        const addRow = (key, value) => {
            const keyInput = h("input", { type: "text", value: key, placeholder: "NAME", spellcheck: false });
            const valueInput = h("input", { type: "text", value, placeholder: "value", spellcheck: false });
            const remove = h("button", { type: "button", className: "btn btn-secondary", textContent: "Remove" });
            const row = h("div", { className: "settings-other-row" }, [keyInput, valueInput, remove]);
            const entry = { read: () => ({ key: keyInput.value, value: valueInput.value }), row };
            remove.addEventListener("click", () => {
                rows.splice(rows.indexOf(entry), 1);
                list.removeChild(row);
            });
            rows.push(entry);
            list.appendChild(row);
        };
        settings.forEach((setting) => addRow(setting.key, setting.value));
        const add = h("button", { type: "button", className: "btn btn-secondary", textContent: "Add row" });
        add.addEventListener("click", () => addRow("", ""));
        const saveBtn = h("button", { type: "button", className: "btn btn-primary", textContent: "Save" });
        saveBtn.addEventListener("click", () => {
            const diff = diffOtherRows(settings, rows.map((entry) => entry.read()));
            if (diff.invalid.length) {
                setStatus(`Invalid name(s): ${diff.invalid.join(", ")}`, true);
                return;
            }
            save(diff, "Other settings saved.");
        });
        return h("section", { className: "settings-block" }, [
            h("h3", { textContent: "Other" }),
            h("small", {
                className: "settings-help",
                textContent: "Keys no provider declares. They are kept and passed to runs as they are.",
            }),
            list,
            h("div", { className: "settings-actions" }, [add, saveBtn]),
        ]);
    }

    function render() {
        const parts = splitGroups(groups);
        const body = els.settingsBody;
        body.textContent = "";
        if (parts.global) {
            body.appendChild(buildGlobal(parts.global));
        }
        const providers = h("section", { className: "settings-block" }, [
            h("h3", { textContent: "Providers" }),
            h("small", {
                className: "settings-help",
                textContent: "Open a provider that isn't configured, fill in its fields and Save to add it.",
            }),
            ...parts.providers.map(buildProvider),
        ]);
        body.appendChild(providers);
        body.appendChild(buildOther(parts.other));
    }

    async function load() {
        try {
            const result = await request("/api/settings");
            groups = result.groups;
            render();
            setStatus("");
        } catch (error) {
            setStatus(errorMessage(error), true);
        }
    }

    // ---------------------------------------------------------------- import / export

    /** @param {boolean} dryRun */
    async function runImport(dryRun) {
        try {
            const result = await send("/api/settings/import", "POST", {
                text: els.settingsImportText.value,
                mode: els.settingsImportMode.value,
                dry_run: dryRun,
            });
            els.settingsImportResult.textContent =
                (dryRun ? "Preview: " : "Imported: ") + describeImportDiff(result.diff);
            els.settingsImportResult.classList.remove("settings-error");
            if (!dryRun) {
                await load();
                onSettingsChanged();
            }
        } catch (error) {
            els.settingsImportResult.textContent = errorMessage(error);
            els.settingsImportResult.classList.add("settings-error");
        }
    }

    function showImport(text) {
        els.settingsEnvPanel.hidden = true;
        els.settingsImportPanel.hidden = false;
        if (typeof text === "string") {
            els.settingsImportText.value = text;
            els.settingsImportResult.textContent = "Sample loaded: Preview, then Apply.";
        }
    }

    async function loadEnvText() {
        try {
            const result = await request(`/api/settings/env?reveal=${envRevealed ? 1 : 0}`);
            els.settingsEnvText.value = result.text || "# No settings stored.\n";
            els.settingsEnvRevealBtn.textContent = envRevealed ? "Hide secrets" : "Reveal secrets";
        } catch (error) {
            setStatus(errorMessage(error), true);
        }
    }

    async function showEnv() {
        els.settingsImportPanel.hidden = true;
        els.settingsEnvPanel.hidden = false;
        envRevealed = false;
        await loadEnvText();
    }

    function download() {
        const blob = new Blob([els.settingsEnvText.value], { type: "text/plain" });
        const link = h("a", { href: URL.createObjectURL(blob), download: "settings.env" });
        link.click();
        URL.revokeObjectURL(link.href);
    }

    function bind() {
        els.settingsImportBtn.addEventListener("click", () => showImport());
        els.settingsSampleBtn.addEventListener("click", async () => {
            try {
                showImport((await request("/api/settings/sample")).text);
            } catch (error) {
                setStatus(errorMessage(error), true);
            }
        });
        els.settingsEnvBtn.addEventListener("click", showEnv);
        els.settingsImportCloseBtn.addEventListener("click", () => {
            els.settingsImportPanel.hidden = true;
        });
        els.settingsEnvCloseBtn.addEventListener("click", () => {
            els.settingsEnvPanel.hidden = true;
            els.settingsEnvText.value = "";
        });
        els.settingsImportPreviewBtn.addEventListener("click", () => runImport(true));
        els.settingsImportApplyBtn.addEventListener("click", () => runImport(false));
        els.settingsImportFile.addEventListener("change", async () => {
            const file = els.settingsImportFile.files && els.settingsImportFile.files[0];
            if (file) {
                els.settingsImportText.value = await file.text();
            }
        });
        els.settingsEnvRevealBtn.addEventListener("click", () => {
            envRevealed = !envRevealed;
            loadEnvText();
        });
        els.settingsEnvCopyBtn.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(els.settingsEnvText.value);
                setStatus("Copied.");
            } catch {
                setStatus("Copy failed: select the text and copy it by hand.", true);
            }
        });
        els.settingsEnvDownloadBtn.addEventListener("click", download);
    }

    return { bind, load };
}
