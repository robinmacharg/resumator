# Task 4: research run picker, company/URL prefill

**Status:** todo. **Read:** RR5; `role-runs-feature.js` (CV run picker), `research-feature.js`.

## Do

- A run picker on the Research tab (role mode) listing research runs (time, provider/model, ✓/✗, dry run); picking
  a successful run makes it current (`POST …/runs/research/<run>/current`) and refreshes the tab.
- Prefill company and URLs from the current run (company falls back to the role's).
- Node tests.

## Done when

Picking an older run swaps the output and PDF; inputs prefill; tests pass.

## Handover

