# Plan: role research from the DB

**Goal:** bring role-mode research up to the CV pipeline: the Research tab shows the role's stored runs (output,
PDF built on demand, run picker), never the `output/research_output.*` files, and the role CLI can write a research
PDF. File mode (`research_role.py`, `research_format.py`, `/api/research/*`) keeps working.

**Status:** in progress. Branch `feature/20261022-role-research` (from `develop`). Decisions RR1–RR6 in
[design.md](design.md).

**Files** (layout per [../README.md](../README.md)): this index (read every session), [design.md](design.md) (read
only the sections your task links), one file per task under `tasks/`, and [log.md](log.md) (append one entry per
task; read only the last few).

## Tasks

| # | Task | Status |
|---|---|---|
| 1 | [In-memory research formatter](tasks/01-formatter.md) | done |
| 2 | [Research run PDF route](tasks/02-render-route.md) | todo |
| 3 | [Research tab reads the role's current run](tasks/03-tab-current-run.md) | todo |
| 4 | [Research run picker, company/URL prefill](tasks/04-run-picker.md) | todo |
| 5 | [Role CLI: research PDF](tasks/05-cli.md) | todo |
| 6 | [Tests sweep and docs](tasks/06-docs.md) | todo |

Sessions: 1 → 2 stay (backend, small). Fresh session before 3 (frontend). 3 → 4 stay. 5 → 6 can share a session.

## Checking

- Never point a check at the real DB: copy `cv_web/resumator.db` with SQLite's backup API into the scratchpad and
  use `--db` (CLI) or patch `server_roles.DB_PATH` / `store.DB_PATH` (server) to the copy.
- Every task: `python3.13 -m unittest discover -s tests` and `(cd cv_web/static && npm test)` pass (system
  `python3` is 3.9).
- One commit per task. Merges need a merge commit (`git merge --no-ff`).

## Handoff

Task 1 done (committed). Next: task 2, the route; it calls `research_format.render_research_pdf`.

Paste this to start or continue:

```text
Continue the plan in docs/plans/role-research/index.md on branch feature/20261022-role-research (check it's checked
out first). Read its Handoff, the next todo task file and the last few entries of log.md, then do that task only,
following AGENTS.md and docs/plans/README.md. Confirm with me before starting the following task.
```
