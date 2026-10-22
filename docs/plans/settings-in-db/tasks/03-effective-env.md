# Task 3: effective environment; `.env` reads removed

**Status:** todo. **Read:** [design § Effective environment](../design.md#effective-environment), D4, D6, D8, D9,
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

(fill in at the end of the task)
