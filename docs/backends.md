# LLM backends

## Plugin contract (`backends/base.py`)

Every backend lives in `backends/<id>/module.py`. The module exposes `get_backend()`, which returns an object with:

| Member | Purpose |
|---|---|
| `id`, `label` | Provider id (used in `--provider`, the `MODEL_PROVIDER` setting, UI) and display name |
| `timeout_seconds` | Per-attempt timeout used by the pipelines |
| `interrogate(env) -> BackendStatus` | `enabled`, `reason` (shown when disabled), `models`, `default_model`. Must be cheap |
| `model_sequence(env, explicit_model) -> list[str]` | Attempt order. An explicit model means try only that one |
| `run_attempt(*, model_name, prompt_text, env, timeout_seconds, heartbeat_seconds, attempt_index, debug_log_dir, log_prefix, emit_live_output, **extra) -> AttemptResult` | One call. Must not raise for provider errors; return a non-zero `returncode` and put the error in `stderr`. `debug_log_dir` may be None (`--io json` runs): write the attempt log with `provider_clients._write_attempt_log(attempt_log_path(debug_log_dir, name), lines)`, which sends it to stderr and leaves `log_path` None |
| `settings() -> list[SettingSpec]` (optional) | Every env key the backend reads: `key, label, secret, default, kind (text/bool/int/csv/choice), choices, help, advanced`. Feeds `settings_catalog`; absent means "no declared keys" (stored keys show under Other). A test greps the sources, so a new `env.get("KEY")` must be declared |
| `test_connection(env) -> TestResult` (optional) | `ok, message, elapsed_seconds, model`. Absent means `settings_catalog.default_test_connection`: interrogate, then one real "Reply with OK" call on the first model, 60 s cap, no fallback |

`AttemptResult` (`provider_clients.py`) has these fields: `provider, model, returncode, stdout, stderr, elapsed_seconds,
log_path, timed_out`. `stdout` is the model's text. `log_path` is None when no log file was written.

## Discovery (`backend_registry.py`)

- Every call scans `backends/*/module.py` sorted by folder name and imports it as `cvgen_backend_<folder>`. Nothing
  is cached, so each `/api/state` re-interrogates (and so re-health-checks the bridge).
- If an import fails or `interrogate` raises, the backend is registered disabled with the reason. Duplicate ids:
  the first one wins.
- `load_backend_objects()` instantiates the backends without interrogating them (used by `settings_catalog`, so
  listing settings never health-checks or autostarts the bridge).
- Default provider = the first enabled backend, alphabetically. The `MODEL_PROVIDER` setting and `--provider` override it.
- `provider_catalog.load_provider_catalog(env)` is the registry's catalog; `model_providers.json` is gone (D10).
- Config comes from the DB, never `.env`: `settings_env.effective_env(conn)` is the process environment minus every
  catalogued key plus the stored settings (D8). `runtime_env(stored)` is the same rule for discovery.

## How pipelines use a backend

`generate_cv.main` / `research_role.main`: resolve provider → `get_backend_or_raise` → refuse if disabled → loop
`model_sequence`, calling `run_attempt`. A failure moves on to the next model only if stderr looks transient
(`is_high_load_error`: 429/503/404, quota, rate limit, model not found). Any other failure aborts. The first success
wins. The whole prompt goes in one user message; there are no system or multi-turn messages (except the bridge's
optional `VSCODE_BRIDGE_SYSTEM_PROMPT`).

## Current backends

| id | Transport | Enabled when | Model env (primary / fallbacks CSV) | Other env |
|---|---|---|---|---|
| `claudecode` | `claude -p` CLI subprocess. The prompt goes on stdin; output is `--output-format json` and the model text is its `result`. Runs from an empty temp dir with `--tools "" --safe-mode --no-session-persistence` and its own `--system-prompt`, so no project or user context leaks in. Uses the CLI's own login (subscription or API key) | `claude` on PATH and `BACKEND_CLAUDECODE_ENABLED` ≠ false | `CLAUDECODE_MODEL` (default `opus`; aliases `opus`, `sonnet`, `fable`, `haiku` or a full id) / `CLAUDECODE_MODEL_FALLBACKS` | `CLAUDECODE_SYSTEM_PROMPT`, `CLAUDECODE_EFFORT` (`--effort`). An API error status (404/429/503) goes into stderr so model fallback works |
| `gemini` | `gemini` CLI subprocess (`--skip-trust --model M --prompt P`), uses the CLI's own auth | always | `GEMINI_MODEL` / `GEMINI_MODEL_FALLBACKS`. Built-in fallback list is appended | `CV_FAST_MODE` (picks the flash-lite default), `GEMINI_CLI_TRUST_WORKSPACE`, `RESEARCH_GEMINI_*` 429 tuning |
| `huggingface` | HTTP OpenAI-style chat completions, `HUGGINGFACE_API_URL` (default HF router) | `HF_API_TOKEN` / `HUGGINGFACE_API_TOKEN` set | `HUGGINGFACE_MODEL` / `HUGGINGFACE_MODEL_FALLBACKS` | `HUGGINGFACE_MAX_RETRIES`, `HUGGINGFACE_INITIAL_BACKOFF_SECONDS` |
| `openai` | HTTP chat completions, `OPENAI_API_URL` | `OPENAI_API_KEY` / `OPENAI_TOKEN` set | `OPENAI_MODEL` / `OPENAI_MODEL_FALLBACKS` | `OPENAI_MAX_RETRIES`, `OPENAI_INITIAL_BACKOFF_SECONDS` |
| `swiftlet` | HTTP chat completions to a local server, `SWIFTLET_API_URL` (default `127.0.0.1:8080/v1/chat/completions`) | always (no health check, so it fails at run time if the server is down) | `SWIFTLET_MODEL` / `SWIFTLET_MODEL_FALLBACKS` | `SWIFTLET_MAX_RETRIES`, `SWIFTLET_INITIAL_BACKOFF_SECONDS` |
| `vscodebridge` | HTTP `POST {prompt, systemPrompt?}` to the VS Code extension (`VSCODE_BRIDGE_API_URL`, default `127.0.0.1:8766/generate`), which calls Copilot via `vscode.lm` | `BACKEND_VSCODEBRIDGE_ENABLED` ≠ false, and either `/health` reports `modelReady` or autostart is on | `VSCODE_BRIDGE_MODEL` (label only; the extension picks the Copilot model) | `VSCODE_BRIDGE_API_KEY` (`x-api-key`), `_AUTOSTART` (default true, runs `VSCodeExtension/start_isolated_bridge.sh` or `_STARTUP_CMD`), `_STARTUP_TIMEOUT_SECONDS`, `_MAX_RETRIES`, `_INITIAL_BACKOFF_SECONDS`, `_SYSTEM_PROMPT` |

Note: the default provider is the first enabled backend alphabetically, which is now `claudecode` whenever `claude`
is installed. Set the `MODEL_PROVIDER` setting to choose a different default.

The HTTP clients send `temperature: 0.2`, retry with exponential backoff on retryable statuses, and write a debug log
for every attempt.

## Adding a backend

1. Create `backends/<id>/module.py` with a class implementing the protocol and `get_backend()`. Copy
   `backends/openai/module.py` (the smallest HTTP example) or `backends/claudecode/module.py` (the simplest CLI
   subprocess example).
2. Put the transport in `provider_clients.py` as `run_<id>_attempt(...)`. Follow an existing HTTP runner for
   retry, backoff, log and `AttemptResult` handling.
3. Declare its env keys in `settings()` (secrets flagged). In `interrogate`, disable the backend with a clear `reason` when credentials or config are missing.
4. Document its env vars in the table above.
5. No registry, server or UI changes are needed; it appears in the provider dropdown automatically.

Duplication to be aware of: `_split_csv` and `_dedupe` are copied into each module, and `research_role.py` keeps its
own `DEFAULT_*_MODEL` constants that duplicate the backend modules ([gaps.md](gaps.md)).
