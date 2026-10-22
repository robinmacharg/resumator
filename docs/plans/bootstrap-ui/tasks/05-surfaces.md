# Task 5: surfaces: panes, sidebar, dialogs, Settings, status bar

**Status:** todo. **Read:** [design § Class mapping](../design.md#class-mapping), [§ Risks](../design.md#risks).

## Do

- Editor and preview panes and inner sections → card-like surfaces (white, theme border, B4 radius, no shadow).
- Role sidebar list → `list-group` / `list-group-item` (`.active`, closed-role dimming kept); built in
  `renderSidebar` in `role-workspace-feature.js`.
- Dialogs (`newRoleDialog`, `firstRunDialog`, `mergeDialog`, `historyDialog`, `settingsDialog`): keep `<dialog>`
  and their JS; inner markup gets modal-style header/body/footer; `::backdrop` themed. Merge/history items and
  badges → `badge text-bg-*`; diff colours from theme tokens.
- Settings provider cards → `card`; status badges → `badge`; errors → `text-danger` / `alert` as fits.
- Status bar and role title row restyled with theme tokens; `setStatus` in `output-display-feature.js` should use a
  class (`text-danger`) instead of inline hex colours.

## Done when

No surface uses the old cream/brown palette (`grep -nE '#(f4efe8|fffaf3|d6cec2|f7f2ec)'`); dialogs open, close and
submit as before; tests pass (update any that assert inline colour); screenshots compared.

## Handover

(empty)
