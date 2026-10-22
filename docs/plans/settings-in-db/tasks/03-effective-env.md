# Task 3: effective environment; `.env` reads removed

**Status:** done. **Read:** [design § Effective environment](../design.md#effective-environment), D4, D6, D8, D9,
D10, D11.

## Do

- `settings_env.py` (repo root): `effective_env(conn)` = `os.environ` minus `catalog_keys()`, plus DB rows.
- `backend_registry.runtime_env(overrides)`; drop its `.env` read. Server `/api/state` passes the DB env.
- `role_runner.run_cv` / `run_research` pass `env=effective_env(conn)`.
- `generate_cv` / `research_role`: no `.env` read in either mode; one-shot opens the DB (`--db`, default
  `cv_web/resumator.db`) and applies D9 (`getpass` on a TTY with offer to save, else fail with how to set it).
  Delete `generate_cv.load_dotenv_file`.
- `cv_convert.py` / `research_format.py`: take theme and font priority from the passed env, not `os.environ`.
- Flags: `--fast`, `--font-priority` (D11).
- Remove `model_providers.json`, `provider_catalog`'s file fallback and `server_request_parsing.MODEL_CATALOG_PATH`.

## Done when

Tests: shell values for catalogued keys are ignored and DB values win; uncatalogued vars pass through; runner
passes env; one-shot without a key fails cleanly when not a TTY; no code path opens `.env` (grep test).

## Handover

- `settings_env.py`: `effective_env(conn, base)`, `resolve_env(stored, base)`, `shadowed_keys` (for task 4's warning),
  `one_shot_env(db_path, provider, overrides)`, `ensure_provider_secret` (D9; raises `SettingsError`).
- Wired: `backend_registry.runtime_env(stored)`; `provider_catalog.load_provider_catalog(env)`; server
  `load_catalog` reads the DB via `server_roles.settings_env()`; `role_runner.run_cv/run_research` default `env` to
  `effective_env(conn)`; `render_cv` / `convert_markdown_outputs` / `preferred_font` take `env`
  (`server_roles.render_run` passes it; `cv_convert` and `research_format` CLIs read the DB);
  `generate_cv.run_cv` / `research_role.run_research` take `env`; one-shot mains resolve it (`--db`, `--fast`,
  `--font-priority` on generate_cv). `--io json` uses its process env as is.
- Removed: `load_dotenv_file` (both scripts), `ENV_FILE`, `model_providers.json`, `MODEL_CATALOG_PATH`, the file
  fallback in `provider_catalog`, the `runtime_env` `.env` read. `env_utils.parse_dotenv_file` stays for import (task 5).
- Left for task 7: `EDITOR_FILES["env"]` and the UI Env tab still read/write `.env` as a plain text file. Nothing
  else reads it. `tests/test_settings_env.py` greps that only `server.py` still mentions it.
- **Until task 9 migrates this install, the real `.env` keys are not used by anything.** Import (task 5) is how
  they get into the DB.
- Not done: `--font-priority`/`--fast` on `research_role`/`cv_convert` (no use there yet); docs still describe `.env` in
  README and the backend env table (task 10).
- Tests: 319 pass on 3.13 (`test_settings_env.py` 12, role_runner default-env test).
