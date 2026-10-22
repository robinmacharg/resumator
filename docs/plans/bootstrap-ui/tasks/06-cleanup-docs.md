# Task 6: dead CSS removal and docs

**Status:** todo. **Read:** [design § Decisions](../design.md#decisions).

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

(empty)
