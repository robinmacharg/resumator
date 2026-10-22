# Task 2: buttons

**Status:** todo. **Read:** [design § Class mapping](../design.md#class-mapping), B3, B9.

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

(empty)
