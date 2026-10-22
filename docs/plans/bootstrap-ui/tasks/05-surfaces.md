# Task 5: surfaces: panes, sidebar, dialogs, Settings, status bar

**Status:** done. **Read:** [design § Class mapping](../design.md#class-mapping), [§ Risks](../design.md#risks).

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

- Panes, sidebar box, logs/research shells, Settings cards and tools: own rules kept (white `--panel`, `--line`
  border, `--bs-border-radius-lg`); no `card` class, since `.card` fills with `--bs-body-bg` (pale blue) and is a
  flex column, awkward on the Settings `<details>`. `--section-surface-bg` removed.
- Role list and CV history: `list-group` on the `ul`, `list-group-item list-group-item-action` on each button (the
  `li` wrappers stay, so items are separate bordered tiles with a 0.25rem gap). `theme.css` `.list-group`: white
  items, ink text, active = pale primary tint (`--bs-primary-bg-subtle`), not solid blue. Old left brand border gone.
- Dialogs: `<dialog>` is the modal box (`theme.css` `dialog`: no padding, border, radius-lg, white; defines the
  `--bs-modal-*` vars Bootstrap only sets on `.modal`); inner markup `modal-header` (`h2.modal-title`, 1.25rem),
  `modal-body`, `modal-footer` (kept `role-dialog-actions` as a hook). One `dialog::backdrop` (black 50%). Settings:
  white header with `btn-close` (was a × glyph), body `modal-body settings-body` holding toolbar, tabs and scroll;
  dialog background stays pale so the white cards stand out.
- Badges: merge `badge text-bg-{success|secondary|danger}` via `STATUS_BADGE` in `role-merge-feature.js`; Settings
  `badge text-bg-primary` (enabled) / `text-bg-light border` (not configured). Diff lines use
  `--bs-success-bg-subtle` / `--bs-danger-bg-subtle`; autoscroll pill uses the warning subtle tokens.
- Errors: `settings-error` → `text-danger` in `settings-feature.js`; dialog errors `merge-error text-danger` (the
  class keeps only `min-height`); `setStatus` / `setResearchStatus` toggle `text-danger` instead of inline hex.
- Old palette grep clean (it already was after task 1). Remaining hex in our CSS: the dark log `pre` and `theme.css`
  danger shades. No test needed changing (they match classes by regex or stub `setStatus`).
- Screenshot kit in this session's scratchpad:
  `/private/tmp/claude-502/-Users-rmacharg-dev-projects-Resumator/0541612c-f0e9-402d-85d7-cc471315be38/scratchpad/`
  (`launch.py` port 8823, `shoot.mjs` gains 11-history, 12-first-run, 13-settings-card; `shots/after-t5/`).
