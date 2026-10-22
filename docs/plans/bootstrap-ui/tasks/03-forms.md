# Task 3: form controls

**Status:** done. **Read:** [design § Class mapping](../design.md#class-mapping).

## Do

- Selects (`.model-picker select`, provider/model/theme/run/status/CV source) → `form-select form-select-sm`;
  label layout stays ours.
- Single-line inputs (new role dialog, research company/URLs, role name input, Settings fields) → `form-control`
  (`-sm` in toolbars). The big editor textareas keep their own monospace look but take the theme border/radius.
- Checkboxes (`.inline-toggle`, steering, dry run, Settings toggles) → `form-check` markup.
- Drop the matching custom rules; keep the role name input sized to the title.
- JS-built inputs in `settings-feature.js` and `role-merge-feature.js` get the same classes.

## Done when

All controls share one height and focus ring per size; tests pass; screenshots compared.

## Handover

- Sizes: regular `form-select` / `form-control` beside regular buttons (header pickers, Run/Theme, sidebar Status,
  debug log, import mode, new-role dialog, research company); `-sm` beside `btn-sm` (CV source select, every
  Settings field and Other row, import file). `theme.css` matches their font/padding to `.btn` / `.btn-sm` and fills
  them white (Bootstrap uses `--bs-body-bg`, our pale blue).
- Checkboxes: Steer and Dry run are `form-check form-check-inline inline-toggle` labels wrapping a
  `form-check-input`; merge checkboxes/radios get `form-check-input` only.
- Deleted: `.model-picker select` look and `:disabled`, generic `select` and text-`input` rules (common.css),
  `.research-input-grid input`, `#researchCompanyInput` height (research.css). Kept: `.model-picker .form-select` and
  `.file-actions .form-select` at `width: auto` (Bootstrap's 100% squeezed the toolbar), `.role-name-input` sizing.
- Editor textareas stay ours (monospace, no `form-control`) with `--bs-border-radius` and Bootstrap's focus ring.
