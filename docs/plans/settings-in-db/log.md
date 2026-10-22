# Settings in the DB: log

Agent log for [index.md](index.md), newest entry last. Append one entry per task; earlier entries are history,
not instructions.

## Log

- 2026-10-22 · Design · Sketched the move from `.env` to the DB. User decisions D1–D11: new `env_setting` table;
  plain-text secrets for now with a Security TODO for backups; real-call provider test; `.env` never read and the
  startup audit refuses to run while one exists (import excepted); fast mode stays global; one-shot scripts read the
  DB; shell env can't override catalogued keys, one rule for all keys, with CLI flags for one-off overrides; no
  secrets on the command line (`getpass` instead); `model_providers.json` removed; `~/.gemini/.env` is a warning only.
- 2026-10-22 · Task 1 · Migration 2 adds `env_setting(key, value, updated_at)` with a key-format CHECK. Store gains
  `list_env_settings`, `env_settings`, `get_env_setting`, `set_env_setting` (`updated_at` moves only on change),
  `delete_env_setting`, `replace_env_settings`. Six tests in `EnvSettingTests`; 294 tests pass on 3.13. Migration
  checked on a backup-API copy of the real DB (v1 → v2, roles intact).
- 2026-10-22 · Process · Plan split into index, design, per-task files and log; layout and session policy recorded
  in `docs/plans/README.md` and `AGENTS.md`.
- 2026-10-22 · Task 2 · `SettingSpec`/`TestResult` in `backends/base.py`; `settings()` on all six backends;
  `settings_catalog.py` (globals, `catalog`, `catalog_keys`, default and dispatching provider test);
  `backend_registry.load_backend_objects` (no interrogation). 12 new tests incl. a source grep that every key read
  is declared; 306 pass on 3.13.
- 2026-10-22 · Task 3 · `settings_env.py` (effective env, one-shot env with `getpass` prompt per D9). All `.env` and
  `model_providers.json` reads removed from the server, runner, scripts, `cv_convert`, `research_format` and
  `provider_catalog`; `env` threaded through rendering. Env tab left for task 7. 319 tests pass on 3.13.
- 2026-10-22 · Task 4 · `startup_audit.py` (dotenv error; model_providers.json, ~/.gemini/.env, shell-shadow warnings) wired into the server, role CLI and one-shot scripts; `--io json` skipped. 13 new tests; 332 pass on 3.13. The repo's real `.env` now blocks startup until imported (task 5).
- 2026-10-22 · Task 5 · `env_utils.parse_dotenv_text`; `settings_io.py` (import merge/replace/dry-run diffs of key lists, `env_from_environment`, masked or revealed `env_export`); `examples/settings.example.env`; role CLI actions `settings-import`/`-export`/`-set`/`-test`. 20 new tests; 352 pass on 3.13.
- 2026-10-22 · Task 6 · `cv_web/server_settings.py` (GET/PUT `/api/settings`, reveal, env text, import, test), routed via `server_roles.dispatch` with a new PUT route table and `do_PUT`. Fixed `is_secret` ignoring the name heuristic for "Other" keys. 12 new tests; 364 pass on 3.13.
- 2026-10-22 · Process · ER diagram moved from `multi-role-design.md` to `docs/db-schema.md` (now includes `env_setting`, schema version 2), linked from AGENTS.md and architecture.md; AGENTS.md says schema changes update it.
- 2026-10-22 · Task 7 · Settings pop-over, opened from a header cog (first built as a sub-tab, then moved on request) (`settings-feature.js`, pure `settings-model.js`, `styles/settings.css`) replaces the Env tab; `EDITOR_FILES["env"]` and the frontend env draft code removed. API gained backend `status` and `GET /api/settings/sample`. 14 new frontend tests (108 pass), 366 Python tests pass on 3.13. Smoke-tested over HTTP on a DB copy; visual layout not checked in a browser.
