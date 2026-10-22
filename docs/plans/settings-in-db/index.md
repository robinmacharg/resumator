# Plan: settings in the DB (removing `.env`)

**Goal:** no file-based config. Runtime config (provider keys, models, tuning, fast mode) lives only in
`cv_web/resumator.db`. A cold start (no DB) lets you import and edit the values; `.env` is removed. The only config
files left are fictional samples under `examples/`. A Settings UI covers adding and testing providers, the global
options, and viewing the settings as a `.env`. Scope is config only; content files (`input/prompt.md`, CVs) are a
separate TODO item.

**Status:** DONE, merged to `develop`. Design agreed (D1–D11). Tasks 1–10 done. Branch `feature/20261022-settings-db` (from `develop`).

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
| 5 | [Import/export core and role CLI](tasks/05-import-export-cli.md) | done |
| 6 | [Settings API](tasks/06-api.md) | done |
| 7 | [Settings UI panel](tasks/07-ui.md) | done |
| 8 | [First-run Settings step](tasks/08-first-run.md) | done |
| 9 | [Migrate this install and cold-start test](tasks/09-migrate-install.md) | done |
| 10 | [Docs](tasks/10-docs.md) | done |

Sessions: expected stay pairs are 2 → 3 (the catalog feeds the effective env) and 6 → 7 (API then its UI). Start
fresh after 3, 5 and 8, and before 9 (it touches real data).

## Handoff

All tasks are done, checked by the user on a cold start, and merged to `develop`. Open follow-up (the user's, outside
this plan): the research preview and Run Log still show `output/` files during the first-run choice. This install now runs from the DB: the real `cv_web/resumator.db` is
restored (schema 2, 22 settings), there's no `.env` in the repo and the startup audit is clean. The user's old file
is at `~/dev/.env` (outside the repo, not read; theirs to delete). Only Gemini works; Hugging Face/OpenAI lack credit
and Swiftlet isn't running, which the user accepts. Still unchecked in a browser: the Settings pop-over and first-run
step (tasks 7–8 Handover). Run Python tests with 3.11+
(`python3.13 -m unittest discover -s tests`); system `python3` and `.venv` are 3.9.6.

Paste this to start or continue:

```text
Continue the plan in docs/plans/settings-in-db/index.md on branch feature/20261022-settings-db (check it's checked
out first). Read its Handoff, the next todo task file and the last few entries of log.md, then do that task only,
following AGENTS.md and docs/plans/README.md.
```
