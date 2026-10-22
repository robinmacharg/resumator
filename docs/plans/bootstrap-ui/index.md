# Plan: Bootstrap UI

**Goal:** move the web UI (`cv_web/templates/index.html`, `cv_web/static/styles/`) onto Bootstrap 5.3 for a flat,
professional look: flat buttons, 2–4px corners, Bootstrap's system font, a very pale blue background. CSS only; the
vanilla-JS behaviour (dialogs, tabs, splitters, sidebar) is unchanged. Ends with our custom CSS cut to what
Bootstrap doesn't cover.

**Status:** done (tasks 1–6; user checked the UI). Decisions B1–B9 agreed. Branch `feature/20261022-bootstrap-ui` (from `develop`).

**Files** (layout per [../README.md](../README.md)): this index (read every session), [design.md](design.md) (read
only the sections your task links), one file per task under `tasks/`, and [log.md](log.md) (append one entry per
task; read only the last few).

## Tasks

| # | Task | Status |
|---|---|---|
| 1 | [Baseline screenshots, vendor Bootstrap, theme tokens, layout fixes](tasks/01-foundation.md) | done |
| 2 | [Buttons](tasks/02-buttons.md) | done |
| 3 | [Form controls](tasks/03-forms.md) | done |
| 4 | [Tabs and sub-tabs](tasks/04-tabs.md) | done |
| 5 | [Surfaces: panes, sidebar, dialogs, Settings, status bar](tasks/05-surfaces.md) | done |
| 6 | [Dead CSS removal and docs](tasks/06-cleanup-docs.md) | done |

Sessions: 2 → 3 → 4 can stay in one session (same files, small diffs). Start fresh after 1 (it sets up the
screenshot tooling) and before 6.

## Checking

- **Never point a UI check at the real DB.** Copy `cv_web/resumator.db` with SQLite's backup API into the
  scratchpad, and launch the server from a small scratchpad script that sets `cv_web.server_roles.DB_PATH` to the
  copy before starting (the server has no `--db` flag). Use another port if 8765 is in use.
- Screenshots: headless Chrome (`/Applications/Google Chrome.app`, `--headless --screenshot --window-size=1600,1000`)
  or the `run` skill. Views: CV tab, Research tab, Logs tab, sidebar with roles, new-role dialog, merge dialog,
  Settings. Keep task 1's baseline set in the scratchpad for later comparison.
- Every task: `(cd cv_web/static && npm test)` and `python3.13 -m unittest discover -s tests` pass (system
  `python3` is 3.9).

## Handoff

Plan done: tasks 1–6 committed on `feature/20261022-bootstrap-ui`, one commit per task (B9). Next: merge to
`develop` when the user asks. Styles are documented in `cv_web/static/ARCHITECTURE.md` § Styles. Gotcha for later
CSS work: a feature rule that sets `display` on a `.tab-panel` element beats `.tab-panel`'s hidden state.

Paste this to start or continue:

```text
Continue the plan in docs/plans/bootstrap-ui/index.md on branch feature/20261022-bootstrap-ui (check it's checked
out first). Read its Handoff, the next todo task file and the last few entries of log.md, then do that task only,
following AGENTS.md and docs/plans/README.md.
```
