# Task 10: docs

**Status:** todo. **Read:** the "Doc upkeep" rule in AGENTS.md; the docs named below.

## Do

- `docs/backends.md`: env vars are now settings keys; precedence (D8, D11); `settings()` / `test_connection()`.
- `docs/architecture.md`, `cv_web/static/ARCHITECTURE.md`: settings flow, endpoints, Settings panel.
- `AGENTS.md`: `.env` invariant → "the DB holds keys; never echo them"; the audit; the settings CLI actions.
- `docs/plans/multi-role-design.md`: note that D6 supersedes R5 for config. (The ER diagram, with `env_setting`, already moved to `docs/db-schema.md`.)

## Done when

No doc mentions `.env` as live config (grep), except history and import.

## Handover

(fill in at the end of the task)
