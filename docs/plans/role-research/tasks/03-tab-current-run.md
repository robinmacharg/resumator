# Task 3: Research tab reads the role's current run

**Status:** todo. **Read:** RR4, [design § Frontend](../design.md#frontend); `cv_web/static/ARCHITECTURE.md`;
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

