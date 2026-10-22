# Task 3: form controls

**Status:** todo. **Read:** [design § Class mapping](../design.md#class-mapping).

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

(empty)
