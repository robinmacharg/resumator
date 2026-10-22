# Bootstrap UI: design

Design record for [index.md](index.md). Tasks link to the sections they need; read only those. Decisions are
numbered B1–B9 and cited by number in tasks and the log.

## Decisions

| # | Decision | Why |
|---|---|---|
| B1 | **Bootstrap 5.3 CSS only, vendored** at `cv_web/static/styles/vendor/bootstrap.min.css` (pinned version, licence header kept) | Local tool: works offline, no build step, no Python dep. Under `styles/` so `handle_static_get` serves it without a server change |
| B2 | **No Bootstrap JS.** Native `<dialog>`, our tab code, splitters and sidebar stay; only their styling changes | They work and are tested (`npm test`); Bootstrap modals/tabs would mean rewriting both for no visible gain |
| B3 | **Flat look:** no gradients, no shadows, solid fills, outline variants for secondary actions | User's call |
| B4 | **Corners 2–4px**: `--bs-border-radius: 0.1875rem` (3px), `-sm` 2px, `-lg` 4px; pills/badges follow | User's call |
| B5 | **Bootstrap's default system font stack**; Avenir Next removed. Monospace via `--bs-font-monospace` | User's call |
| B6 | **Very pale blue page background** (start at `#f3f6fa`; panels/cards white, lines `#dee2e6`-ish) | User's call: more professional than the cream |
| B7 | **Primary is Bootstrap's default blue `#0d6efd`** (no override; links and focus ring follow). Danger stays `#b42318`. Teal `#005f73` dropped | User's call at the task 1 review: a medium blue |
| B8 | **All overrides in one file**, `styles/theme.css`, loaded after Bootstrap and before our feature CSS: `--bs-*` variables plus our `--brand`/`--line`/… tokens mapped onto them | One place to retune the look |
| B9 | **Migrate by area, one commit per task**; delete our rule for a thing in the same commit that moves it to Bootstrap classes | Our `.btn`, `.btn-primary`, `.btn-secondary` collide with Bootstrap's names; half-migrated states look broken |

## Load order

`index.html` `<head>`: `styles/vendor/bootstrap.min.css` → `styles.css` (which `@import`s `theme.css` first, then
`common.css`, `cv.css`, …). Strip the trailing `sourceMappingURL` comment from the vendored file (no map served).

## Class mapping

| Ours now | Bootstrap target |
|---|---|
| `.btn.btn-primary` (gradient) | `.btn.btn-primary` (flat, B3) |
| `.btn.btn-secondary` | `.btn.btn-outline-secondary` (or `btn-light` for toolbar buttons; pick one, record it) |
| `.icon-btn`, settings cog | `.btn.btn-sm.btn-outline-secondary` + our size tweak |
| `.model-picker select` | `.form-select.form-select-sm`; label stays ours |
| text inputs, textareas (editors excluded) | `.form-control` / `.form-control-sm` |
| `.inline-toggle` checkbox | `.form-check` + `.form-check-input` |
| `.tabbar` / `.tab-btn` | `.nav.nav-tabs` / `.nav-link` (`.active` already toggled by JS) |
| sub-tabs (`cv-subtab-btn`, `research-*-tab-btn`, `settings-tab-btn`, log tabs) | `.nav.nav-underline` or `.nav-tabs.nav-sm`; one style for all |
| `.role-dialog`, `.merge-dialog`, `.settings-dialog` | keep `<dialog>`; inner markup styled like `.modal-content` / `-header` / `-body` / `-footer` |
| `.editor-pane`, `.preview-pane`, sections | `.card`-like surface (white, border, B4 radius) |
| role list | `.list-group` / `.list-group-item` (`.active` already toggled) |
| badges (`merge-badge`, settings status) | `.badge` with `text-bg-*` |
| status bar | stays ours, restyled with theme tokens |

JS that builds class names (`role-item`, `merge-*`, `history-item`, `settings-error`, …) gets Bootstrap classes
added beside ours; keep our classes as hooks the tests and JS query.

## Risks

- **Reboot** changes base font size, margins, `box-sizing` and heading sizes: the flex/grid full-height layout
  (`body` column flex, `.layout` grid, research splitters) needs checking first (task 1).
- **`[hidden]`**: any of our rules setting `display` override `hidden`; Bootstrap doesn't fix that. Keep explicit
  `[hidden] { display: none }` guards (see `.role-title-btn[hidden]`).
- **No visual tests.** Each task compares before/after screenshots (index § Checking).
- Bootstrap's `.active`, `.show`, `.disabled`, `.hidden`-style names could clash with ours: grep before reusing.
