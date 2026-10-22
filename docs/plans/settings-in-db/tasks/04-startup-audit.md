# Task 4: startup audit

**Status:** todo. **Read:** [design § Startup audit](../design.md#startup-audit), D7, D11.

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

(fill in at the end of the task)
