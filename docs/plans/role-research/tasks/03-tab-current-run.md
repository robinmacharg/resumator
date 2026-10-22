# Task 3: Research tab reads the role's current run

**Status:** done. **Read:** RR4, [design § Frontend](../design.md#frontend); `cv_web/static/ARCHITECTURE.md`;
`research-feature.js`, `pdf-preview-feature.js`, `output-display-feature.js`, `app.js` (`afterRoleResearchRun`),
`role-workspace-feature.js` (role select).

## Do

- Role mode: after a research run and on role select, load the current research run; show its `outputMd` in the
  output pane and the task-2 PDF route in the research preview. No current run → empty state, not `output/` files.
- Hide the Format button in role mode. File mode unchanged.
- Node tests for the new wiring.

## Done when

On a DB copy: running research (or a dry run) updates the tab's output and PDF; switching roles swaps them; tests
pass.

## Handover

- `research-feature.js` `loadRoleResearch(roleId, {keepConsole})`: `GET …/runs` → current research run →
  `GET …/runs/research/<run>`; console = `outputMd`, else `outputJson.output` (dry run); built query =
  `outputJson.promptPreview`. Preview source URL is the task-2 route, or null with "Run #N has no output (dry run)."
  when `outputMd` is blank (the route would 409). Drops a reply for a role no longer active.
- Called by `role-workspace-feature.js` (`ctx.loadRoleResearch`, late-bound in `app.js`) in `selectRole`, and with
  null in `openMasterOnly` and the first-run path. `runResearch` calls it after a role run with `keepConsole` when
  the run failed or was stopped, so the failure log stays visible (failed runs are never current).
- `pdf-preview-feature.js`: `runSources = {cv, research}`; `setResearchRunSource`; `renderRunPreview(kind)`.
- Format button: `data-file-only` in `cv_web/templates/index.html`.
- Not done (task 4): company/URL prefill and the run picker. On startup the file-mode `/api/research/state` still
  fills company/URL inputs from `output/`; task 4 replaces that with the run's values.
- Checked on a DB copy via API (scratchpad smoke script): current run PDF 200, dry-run current 409, page has the
  file-only Format button. Not clicked through in a browser.

