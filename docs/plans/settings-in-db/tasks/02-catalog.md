# Task 2: settings catalog and backend contract

**Status:** todo. **Read:** [design § Settings catalog](../design.md#settings-catalog-code),
[§ Provider test](../design.md#provider-test), D3, D11; `backends/base.py`; the env table in `docs/backends.md`.

## Do

- `backends/base.py`: `SettingSpec` dataclass and `TestResult`; optional `settings()` and `test_connection(env)`
  members (absent means "no declared keys" / the default test).
- `settings_catalog.py` (repo root): global specs (`MODEL_PROVIDER`, `CV_FAST_MODE`, `CV_THEME`, `CV_FONT_PRIORITY`,
  `RESEARCH_GEMINI_*` as Advanced, `GEMINI_CLI_TRUST_WORKSPACE`); `catalog(env)` grouped as Global / per backend /
  Other; `catalog_keys()`; `default_test_connection(backend, env)` (interrogate + one tiny `run_attempt`, first
  model, short timeout, no fallback).
- `settings()` on every backend in `backends/*/module.py`, covering every key that backend reads (grep
  `env.get(`); secrets flagged (`*_API_KEY`, `*_TOKEN`, `GEMINI_API_KEY`).

## Done when

Tests: every key read in code appears in `catalog_keys()` (a grep-style test over the sources); unknown DB keys
land in Other; the default test returns `ok` / an error message with a fake backend.

## Handover

(fill in at the end of the task)
