const state = {
  isRunning: false,
  logsVisible: false,
};

const els = {
  statusText: document.getElementById("statusText"),
  cvEditor: document.getElementById("cvEditor"),
  promptEditor: document.getElementById("promptEditor"),
  jobspecEditor: document.getElementById("jobspecEditor"),
  saveBtn: document.getElementById("saveBtn"),
  refreshDiskBtn: document.getElementById("refreshDiskBtn"),
  runFormatBtn: document.getElementById("runFormatBtn"),
  runFullBtn: document.getElementById("runFullBtn"),
  toggleLogsBtn: document.getElementById("toggleLogsBtn"),
  logsPanel: document.getElementById("logsPanel"),
  runLogOutput: document.getElementById("runLogOutput"),
  debugLogOutput: document.getElementById("debugLogOutput"),
  refreshLogsBtn: document.getElementById("refreshLogsBtn"),
  logSelect: document.getElementById("logSelect"),
  pdfPreview: document.getElementById("pdfPreview"),
};

const LS_KEYS = {
  cv: "cvweb.cv",
  prompt: "cvweb.prompt",
  jobspec: "cvweb.jobspec",
};

function setStatus(message, isError = false) {
  els.statusText.textContent = message;
  els.statusText.style.color = isError ? "#b42318" : "#1f1f1f";
}

function setRunning(running) {
  state.isRunning = running;
  [els.saveBtn, els.refreshDiskBtn, els.runFormatBtn, els.runFullBtn].forEach((btn) => {
    btn.disabled = running;
  });
}

function currentFiles() {
  return {
    cv: els.cvEditor.value,
    prompt: els.promptEditor.value,
    jobspec: els.jobspecEditor.value,
  };
}

function writeDraftToLocalStorage() {
  const files = currentFiles();
  localStorage.setItem(LS_KEYS.cv, files.cv);
  localStorage.setItem(LS_KEYS.prompt, files.prompt);
  localStorage.setItem(LS_KEYS.jobspec, files.jobspec);
}

function hasLocalDraft() {
  return [LS_KEYS.cv, LS_KEYS.prompt, LS_KEYS.jobspec].some((key) => localStorage.getItem(key) !== null);
}

function loadLocalDraft() {
  const cv = localStorage.getItem(LS_KEYS.cv);
  const prompt = localStorage.getItem(LS_KEYS.prompt);
  const jobspec = localStorage.getItem(LS_KEYS.jobspec);

  if (cv !== null) {
    els.cvEditor.value = cv;
  }
  if (prompt !== null) {
    els.promptEditor.value = prompt;
  }
  if (jobspec !== null) {
    els.jobspecEditor.value = jobspec;
  }
}

function applyFilesToEditors(files) {
  els.cvEditor.value = files.cv || "";
  els.promptEditor.value = files.prompt || "";
  els.jobspecEditor.value = files.jobspec || "";
}

async function api(path, options = {}) {
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

function updatePreviewCacheBuster() {
  const ts = Date.now();
  els.pdfPreview.src = `/output/tailored_dev.pdf?ts=${ts}`;
}

function summarizeRun(run) {
  if (!run || typeof run !== "object") {
    return "No run output yet.";
  }

  const summary = [
    `Kind: ${run.kind}`,
    `Exit: ${run.exitCode}`,
    `Elapsed: ${run.elapsedSeconds}s`,
    "",
  ];

  if (run.output) {
    summary.push(run.output);
  } else {
    summary.push("(No process output)");
  }

  return summary.join("\n");
}

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

  [els.cvEditor, els.promptEditor, els.jobspecEditor].forEach((editor) => {
    editor.addEventListener("input", schedule);
  });
}

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
      els.runLogOutput.textContent = summarizeRun(payload.lastRun);
    }
  } catch (err) {
    els.debugLogOutput.textContent = `Unable to load logs: ${err.message}`;
  }
}

async function loadSelectedDebugLog() {
  const name = els.logSelect.value;
  if (!name) {
    els.debugLogOutput.textContent = "Select a debug log to view its content.";
    return;
  }

  try {
    const payload = await api(`/api/logs/content?name=${encodeURIComponent(name)}`);
    els.debugLogOutput.textContent = payload.content || "(Empty log file)";
  } catch (err) {
    els.debugLogOutput.textContent = `Unable to load log file: ${err.message}`;
  }
}

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

async function runPipeline(kind) {
  setRunning(true);
  setStatus(kind === "full" ? "Running full pipeline..." : "Running formatting only...");

  try {
    writeDraftToLocalStorage();
    const payload = await api(kind === "full" ? "/api/run/full" : "/api/run/format", {
      method: "POST",
      body: JSON.stringify({ files: currentFiles() }),
    });

    const run = payload.run || null;
    els.runLogOutput.textContent = summarizeRun(run);
    updatePreviewCacheBuster();
    await refreshLogs();

    if (run && run.success) {
      setStatus(`Run complete (${run.elapsedSeconds}s).`);
    } else {
      setStatus("Run failed. Open logs for details.", true);
    }
  } catch (err) {
    setStatus(`Run failed: ${err.message}`, true);
    els.runLogOutput.textContent = err.stack || err.message;
  } finally {
    setRunning(false);
  }
}

async function reloadFromDisk() {
  setRunning(true);
  setStatus("Reloading from disk...");

  try {
    const payload = await api("/api/state");
    applyFilesToEditors(payload.files || {});
    writeDraftToLocalStorage();
    updatePreviewCacheBuster();
    setStatus("Reloaded from disk.");
  } catch (err) {
    setStatus(`Reload failed: ${err.message}`, true);
  } finally {
    setRunning(false);
  }
}

function toggleLogs() {
  state.logsVisible = !state.logsVisible;
  els.logsPanel.classList.toggle("hidden", !state.logsVisible);
  els.toggleLogsBtn.textContent = state.logsVisible ? "Hide Logs" : "Show Logs";
  if (state.logsVisible) {
    refreshLogs();
  }
}

async function initialize() {
  setStatus("Loading editor state...");
  try {
    const payload = await api("/api/state");
    applyFilesToEditors(payload.files || {});

    if (hasLocalDraft()) {
      loadLocalDraft();
      setStatus("Loaded browser draft. Use Save Files to write to disk.");
    } else {
      writeDraftToLocalStorage();
      setStatus("Loaded from disk.");
    }

    if (payload.lastRun) {
      els.runLogOutput.textContent = summarizeRun(payload.lastRun);
    }

    updatePreviewCacheBuster();
  } catch (err) {
    setStatus(`Initialization failed: ${err.message}`, true);
  }
}

els.saveBtn.addEventListener("click", saveToDisk);
els.refreshDiskBtn.addEventListener("click", reloadFromDisk);
els.runFormatBtn.addEventListener("click", () => runPipeline("format"));
els.runFullBtn.addEventListener("click", () => runPipeline("full"));
els.toggleLogsBtn.addEventListener("click", toggleLogs);
els.refreshLogsBtn.addEventListener("click", refreshLogs);
els.logSelect.addEventListener("change", loadSelectedDebugLog);

bindAutosave();
initialize();
