# Task 2: buttons

**Status:** done. **Read:** [design § Class mapping](../design.md#class-mapping), B3, B9.

## Do

- Delete our `.btn`, `.btn-primary`, `.btn-secondary` rules in `common.css` (and any per-feature button rules that
  only restate them).
- `index.html`: secondary buttons → the outline/light variant chosen in the mapping (record it in the log); icon
  buttons (`+`, settings cog) → `btn-sm` variant with a size tweak; destructive (Delete role) → `btn-outline-danger`.
- JS-built buttons (grep `createElement("button")` in `static/js/`) get the same classes.
- Keep `.role-title-btn` as is (a text-like button, not a Bootstrap button).

## Done when

Every button is flat Bootstrap, disabled states read clearly, no gradients left (`grep -n gradient styles/`), tests
pass, screenshots compared.

## Handover

- Mapping chosen: every secondary → `btn-outline-secondary` (no `btn-light`). Toolbar buttons (file Load/Save,
  Promote/Pull/Import/History) and Settings' JS-built row buttons → `btn-sm`. Icon buttons (`+`, copy, cog) →
  `btn btn-sm btn-outline-secondary icon-btn`. Delete role → `btn-outline-danger`.
- Deleted from `common.css`: `.btn`, `:hover`, `:disabled`, `.btn-primary`, `.btn-secondary`, `.btn-danger`,
  `.btn-ghost` (unused), `.file-actions .btn`; `.icon-btn` keeps only its size/centring. `settings.css`: `.settings-cog`
  rule gone (class kept as a hook).
- `theme.css`: denser `.btn` (0.875rem) and `.btn-sm` (0.8125rem) via `--bs-btn-*`; `.btn-danger` (Run Research
  while running, toggled in `run-state-feature.js`) and `.btn-outline-danger` repointed at our red.
- `role-item` / `history-item` buttons are list rows, left for task 5. Only gradient left is the splitter grip dots.
