# Task 4: startup audit

**Status:** done. **Read:** [design § Startup audit](../design.md#startup-audit), D7, D11.

## Do

- `startup_audit.py`: `Finding(level, code, message)`, a list of check functions, `run_audit(root, *, allow=())`.
- Checks: `.env`/`.env.*` in the repo (error; skips `.venv/`, `node_modules/`, `VSCodeExtension/runtime/`; the
  message gives the import command); `model_providers.json` present (warn); `~/.gemini/.env` (warn); catalogued
  keys set in the shell and ignored (warn).
- Wire into `python3 -m cv_web`, `python3 -m resumator` (import action passes `allow={"dotenv"}`) and the one-shot
  scripts. Errors print and exit non-zero; warnings print.

## Done when

Tests per check with temp dirs and a patched env; entry points refuse to start on an error (unit-level, not a live
server).

## Handover

- `startup_audit.py`: `Finding`, `CHECKS`, `run_audit(root, *, allow=())`, `audit_or_exit` (prints to stderr, exit 1 on
  error). Codes: `dotenv` (error), `model-providers`, `gemini-home-env`, `shell-shadow` (warn).
- Wired in `cv_web.server.run_server`, `resumator.main` (allows `dotenv` when `--action settings-import`, which
  task 5 must add to `ACTIONS`), and the one-shot `main`s of `generate_cv`, `research_role`, `research_format`,
  `cv_convert`. `--io json` modes skip it (no files, caller-resolved env).
- `settings_env` is imported lazily inside the shadow check: `settings_catalog` imports `cv_convert`, which imports
  `startup_audit`.
- **The real repo has a `.env`**, so the audit now blocks `python3 -m cv_web` and the scripts until task 5's import
  (or task 9). Tests that call `resumator.main` patch `run_audit`; the no-`.env`-read source grep skips
  `startup_audit.py`.
- 332 tests pass on 3.13.
