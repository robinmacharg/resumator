# Task 6: dead CSS removal and docs

**Status:** done (user checked the UI). **Read:** [design § Decisions](../design.md#decisions).

## Do

- Find selectors in `styles/*.css` no longer matched by `index.html` or JS-built markup and delete them; fold
  near-empty feature files if it reads better. Remove unused tokens from `theme.css`.
- Docs: `cv_web/static/ARCHITECTURE.md` (styles layout, Bootstrap vendored, `theme.css` as the place to retune),
  `docs/architecture.md` if it mentions the styles; the AGENTS.md row for this plan already exists. Note the Bootstrap version
  and how to upgrade it (replace file, check SRI, strip map comment).
- Final screenshot set for the user; set plan status to done.

## Done when

No dead selectors left; docs current; tests pass; user has checked the UI in a browser.

## Handover

- Dead selectors: only `#tab-env` (cv.css) and the `--brand-strong` token; found by a scratchpad script that greps
  every class, id and custom property in `styles/*.css` against `index.html`, `app.js` and `js/*.js`.
- Redundant rules removed: Reboot's `box-sizing` and body margin/colour/background, `.role-title-btn[hidden]`
  (Reboot's `[hidden]` is `!important`), duplicated `.pane-splitter` properties (the shared splitter rule has them),
  all `.dragging` rules (background already transparent; JS still toggles the class), `.cv-subpanel label` /
  `.research-input-grid label` (inside `.tab-panel`), `.settings-tool textarea` (global `textarea` covers it).
- Gotcha hit: `.logs { display: grid }` overrode `.tab-panel`'s hidden state, so the Logs panel showed in every tab
  once `.tab-panel.logs` rules went. Fixed at the cause: `.logs` no longer sets `display`.
- Moved `.preview-header a + a` from roles.css to logs-preview.css beside `.preview-header a`. No files folded:
  cv.css (~40 lines) is small but is the CV tab's own area.
- Docs: `cv_web/static/ARCHITECTURE.md` gains a Styles section (files, load order, `theme.css` as the retune point,
  Bootstrap gotchas, upgrade steps: check sha384 before stripping the map comment); `docs/architecture.md` points
  to it. There is no SRI `integrity` on the `<link>` (vendored file, map comment stripped).
- Final screenshots match task 5's except sub-pixel noise in the PDF preview area:
  `/private/tmp/claude-502/-Users-rmacharg-dev-projects-Resumator/80786b29-b6a8-4e6b-82b5-5ac80d78b4d3/scratchpad/shots/final/`
  (kit: `launch.py` port 8823, `shoot.mjs`, `dead.py` in that scratchpad).
