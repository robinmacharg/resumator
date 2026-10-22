# Task 4: research run picker, company/URL prefill

**Status:** done. **Read:** RR5; `role-runs-feature.js` (CV run picker), `research-feature.js`.

## Do

- A run picker on the Research tab (role mode) listing research runs (time, provider/model, ✓/✗, dry run); picking
  a successful run makes it current (`POST …/runs/research/<run>/current`) and refreshes the tab.
- Prefill company and URLs from the current run (company falls back to the role's).
- Node tests.

## Done when

Picking an older run swaps the output and PDF; inputs prefill; tests pass.

## Handover

- `research-feature.js`: `loadRoleResearch` now also fills `state.researchRuns` and `#researchRunSelect`
  (`renderResearchRunSelect`, `researchRunLabel`) and prefills inputs (`prefillResearchInputs`: run company → role
  company → ""; URLs from `urlsJson`). `keepConsole` (after a failed or stopped run) leaves the inputs alone too.
  `handleResearchRunSelectChanged` POSTs `…/runs/research/<run>/current`, reloads; on error it restores the picker.
- Picker markup: `#researchRunSelect` in the Research actions row, `data-role-only data-needs-role`; disabled while
  running (`run-state-feature.js`); change bound in `app-event-bindings-feature.js`.
- Checked in headless Chrome against a server on a DB copy: picker labels, picking run #2 swapped output, PDF,
  company and URLs, Format button hidden. Scripts in the session scratchpad (`serve_copy.py`, `cdp_pick.mjs`).
- The user reported "404 - unknown route" in the research pane after task 3. Not reproduced: the live server (started
  22:49, after the task 2–3 commits) serves the route, the live DB has no research runs (so the pane shows a
  placeholder and makes no request), and a fresh headless load is clean. Only a server without the task 2 route
  answers "Unknown route" for that URL, so it was most likely a stale server process or cached page.

