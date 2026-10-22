# Task 10: docs

**Status:** done. **Read:** the "Doc upkeep" rule in AGENTS.md; the docs named below.

## Do

- `docs/backends.md`: env vars are now settings keys; precedence (D8, D11); `settings()` / `test_connection()`.
- `docs/architecture.md`, `cv_web/static/ARCHITECTURE.md`: settings flow, endpoints, Settings panel.
- `AGENTS.md`: `.env` invariant → "the DB holds keys; never echo them"; the audit; the settings CLI actions.
- `docs/plans/multi-role-design.md`: note that D6 supersedes R5 for config. (The ER diagram, with `env_setting`, already moved to `docs/db-schema.md`.)

## Done when

No doc mentions `.env` as live config (grep), except history and import.

## Handover

- Most docs were already updated by tasks 3–9; this task did AGENTS.md (invariant, audit, declare-new-keys rule),
  README (Settings, first-run import, audit error fix, one-shot scripts read DB config), backends.md (D8/D9/D11
  precedence, CLI settings actions), architecture.md (`EDITOR_FILES` has no `env`; pop-over not sub-tab),
  multi-role-design.md (R5 superseded for config by D6) and gaps.md (stale `.env`-in-git and `load_dotenv_file`
  entries removed: `.env` has no git history and the duplicate parsers are gone).
- Grep check: remaining `.env` mentions are history, import, or "not read" statements.
