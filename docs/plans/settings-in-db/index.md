# Plan: settings in the DB (removing `.env`)

**Goal:** no file-based config. Runtime config (provider keys, models, tuning, fast mode) lives only in
`cv_web/resumator.db`. A cold start (no DB) lets you import and edit the values; `.env` is removed. The only config
files left are fictional samples under `examples/`. A Settings UI covers adding and testing providers, the global
options, and viewing the settings as a `.env`. Scope is config only; content files (`input/prompt.md`, CVs) are a
separate TODO item.

**Status:** IN PROGRESS. Design agreed (D1–D11). Tasks 1–4 done. Branch `feature/20261022-settings-db` (from `develop`).

**Files** (layout per [../README.md](../README.md)): this index (read every session), [design.md](design.md) (read
only the sections your task links), one file per task under `tasks/`, and [log.md](log.md) (append one entry per
task; read only the last few).

## Tasks

| # | Task | Status |
|---|---|---|
| 1 | [Store: `env_setting` table and functions](tasks/01-store.md) | done |
| 2 | [Settings catalog and backend contract](tasks/02-catalog.md) | done |
| 3 | [Effective environment; `.env` reads removed](tasks/03-effective-env.md) | done |
| 4 | [Startup audit](tasks/04-startup-audit.md) | done |
| 5 | [Import/export core and role CLI](tasks/05-import-export-cli.md) | todo |
| 6 | [Settings API](tasks/06-api.md) | todo |
| 7 | [Settings UI panel](tasks/07-ui.md) | todo |
| 8 | [First-run Settings step](tasks/08-first-run.md) | todo |
| 9 | [Migrate this install and cold-start test](tasks/09-migrate-install.md) | todo |
| 10 | [Docs](tasks/10-docs.md) | todo |

Sessions: expected stay pairs are 2 → 3 (the catalog feeds the effective env) and 6 → 7 (API then its UI). Start
fresh after 3, 5 and 8, and before 9 (it touches real data).

## Handoff

Tasks 1–4 are done (4 uncommitted until committed with this handoff). Next is task 5, in a new session (add `settings-import` to `resumator.ACTIONS`; `main` already allows `dotenv` for it). Nothing reads the real `.env`, and the audit now refuses to start the server and scripts while it exists, so until task 5's import the app can't run: that is expected. Run Python tests with Python 3.11+ (`python3.13 -m unittest
discover -s tests`): system `python3` and `.venv` are 3.9.6 and fail 19 pre-existing tests (a `.venv` rebuild is
being handled separately).

Paste this to start or continue:

```text
Continue the plan in docs/plans/settings-in-db/index.md on branch feature/20261022-settings-db (check it's checked
out first). Read its Handoff, the next todo task file and the last few entries of log.md, then do that task only,
following AGENTS.md and docs/plans/README.md.
```
