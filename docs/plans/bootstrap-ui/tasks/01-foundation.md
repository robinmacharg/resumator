# Task 1: baseline screenshots, vendor Bootstrap, theme tokens, layout fixes

**Status:** done. **Read:** [design § Decisions](../design.md#decisions), [§ Load order](../design.md#load-order),
[§ Risks](../design.md#risks), [index § Checking](../index.md#checking).

## Do

- Build the checking setup (DB copy + launcher script, screenshot command) in the scratchpad and take the
  **baseline** screenshots before any change.
- Vendor Bootstrap 5.3.x CSS (B1): fetch the pinned `bootstrap.min.css` from jsDelivr, check it against the
  published SRI hash, keep the licence header, strip `sourceMappingURL`. Note the version and hash in the log.
- Add `styles/theme.css` (B8) and import it first in `styles.css`: radius vars (B4), body font left to Bootstrap
  (remove the `font-family` on `html, body` in `common.css`, B5), body background pale blue (B6), `--bs-primary` /
  `--bs-primary-rgb` / link colours from the teal (B7), danger. Map `--bg`, `--panel`, `--line`, `--brand`, `--ink`,
  `--muted`, `--danger` onto the Bootstrap variables so existing rules follow.
- Link `bootstrap.min.css` before `styles.css` in `index.html`.
- Fix what Reboot breaks in the layout: full-height body flex, `.workspace`, `.layout` grid and splitter, editor
  textareas, research splitters, status bar. No component restyling yet.

## Done when

Page looks like today's layout with the new font, background and colours; nothing overflows or collapses; tests
pass. Show the user before/after screenshots and confirm B7 (teal primary) or record their choice.

## Handover

- Bootstrap **5.3.8** vendored at `cv_web/static/styles/vendor/bootstrap.min.css`; SRI
  `sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB` (matches getbootstrap.com);
  `sourceMappingURL` stripped. Linked before `styles.css` in `index.html`.
- `styles/theme.css` (first `@import` in `styles.css`): danger, pale-blue body bg, radii; primary/link/focus ring
  left at Bootstrap's blue (B7, user's choice at review; `--brand-strong` now `var(--brand)`, so no teal remains);
  maps `--bg`, `--panel` (white), `--surface-muted` (new, `--bs-tertiary-bg`), `--ink`, `--muted`, `--line`,
  `--brand`, `--danger`. `common.css` `:root` now holds only app tokens (`--brand-strong`, `--subtab-*`).
- Cream colours swapped for tokens (topbar, status bar, tab/sub-tab bg, readonly textarea, logs surface, PDF
  placeholder); radial body gradient and topbar blur removed; monospace via `--bs-font-monospace` everywhere.
- Reboot fixes in `common.css`: `h1–h3` weight 700, `dialog h2` 1.5rem, generic `select` and text `input` at
  0.85rem (Reboot makes controls inherit 1rem); `roles.css`: sidebar Status picker fills the width (it overflowed).
- Layout (body flex, `.workspace`, `.layout` grid/splitter, editors, research splitters, status bar) needed no
  change. Reboot also brings `[hidden]{display:none!important}`, which covers the design § Risks `[hidden]` case.
- Class clashes with Bootstrap (grep): only `btn`, `btn-primary`, `btn-secondary`, `btn-danger`, `active`,
  `visible`. Our `.btn*` rules still win (loaded later); task 2 replaces them.
- Checking kit (scratchpad, session-specific, rebuild if gone): DB copy via backup API, `launch.py` (patches
  `store.DB_PATH`, `store.connect` default, `server_roles.DB_PATH`, port **8811**; 8765 and 8799 are held by other
  servers), `shoot.mjs <outdir>` (headless Chrome over CDP with Node's global `WebSocket`; views 01-cv … 06-settings;
  picks the last role, resets to the CV tab each view). Baseline set: `shots/baseline/`. Task 1's copy:
  `/private/tmp/claude-502/-Users-rmacharg-dev-projects-Resumator/180da168-fd88-4d85-9f9b-a48f7c47ecd5/scratchpad/`
  (copy `launch.py`, `shoot.mjs`, `shots/baseline/` into the new session's scratchpad; fix the paths in `launch.py`).
