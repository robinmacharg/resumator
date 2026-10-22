# Task 8: first-run Settings step

**Status:** done. **Read:** [design § Cold start, import, export](../design.md#cold-start-import-export);
`cv_web/first_run.py` and its UI.

## Do

After the example/blank choice, a Settings step: import (paste or file), load the sample, or skip. Reuses task 7's
import dialog.

## Done when

`tests/test_first_run.py` covers the step's API; a cold start on an empty temp DB reaches a usable app.

## Handover

- API: `first_run.status` (so `GET /api/setup`) gains `hasSettings` (any `env_setting` rows). Settings don't count
  as data, so importing before the choice still leaves it due. No new endpoint: the step uses task 7's
  `GET /api/settings/sample` and `POST /api/settings/import`.
- UI: `role-workspace-feature` remembers `!setup.hasSettings` at startup and, after a successful `chooseFirstRun`,
  calls `ctx.openSettingsStep` → `settingsFeature.openFirstRun()` (app.js): the pop-over on the Providers tab with
  the import panel open and a hint. Skip = close it (X, Escape, backdrop). Not shown when settings already exist.
- Tests: `test_first_run` `ColdStartApiTests` (empty DB → choice → sample preview/import → openai enabled, example
  run listed; blank → skip) and a status test; 3 frontend tests. 369 Python / 111 frontend pass.
- Cold start checked over real HTTP (in-process `CVWebHandler`, empty scratch DB, audit bypassed because the repo's
  `.env` still exists): page, setup, import, enabled provider, no secret in `/api/state`. **Not looked at in a
  browser** (same as task 7). The sample's provider test fails as designed (made-up localhost URL); its message is
  the raw HTML tail of whatever answers on :8080, which reads badly; maybe trim non-JSON error bodies later.
