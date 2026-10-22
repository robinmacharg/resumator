# Task 4: tabs and sub-tabs

**Status:** done. **Read:** [design § Class mapping](../design.md#class-mapping), B2.

## Do

- Top tabs (`.tabbar` / `.tab-btn`) → `nav nav-tabs` / `nav-link`; keep `data-tab`, `role`, `aria-selected` and
  our class names as JS hooks (the tab code in `ui-layout-feature.js` and friends selects by them).
- Sub-tabs (CV, research input/output, logs, Settings) → one shared small style (`nav-underline` or compact
  `nav-tabs`); delete the `--subtab-*` variables and rules they replace.
- Dirty markers on tab labels must still show.

## Done when

All tab strips use Bootstrap navs with one sub-tab style; switching still works everywhere (click through); tests
pass; screenshots compared.

## Handover

- Top tabs: `.tabbar` is `nav nav-tabs`, `.tab-btn` is `nav-link` (active bold). Sub-tabs (CV, Settings via
  `cv-subtabbar`, research input/output, logs): `nav nav-underline` + `nav-link`, one compact rule in `common.css`
  (0.8125rem, links overlap the strip's bottom line). Our classes and `data-*` hooks kept.
- `theme.css`: `.nav` links muted (not link blue); `.nav-tabs` active tab white, not `--bs-body-bg`.
- Deleted the `--subtab-*` tokens and old tab rules; `roles.css` merge badge/diff now use `--surface-muted`.
- Dirty markers are text on `.tab-label` spans, unchanged. Scratchpad `shoot.mjs` gained views 07–10 (CV Job Spec,
  research sub-tabs, Logs debug, Settings Providers) to click through every strip. Copy the kit from this session's
  scratchpad instead of task 1's: `/private/tmp/claude-502/-Users-rmacharg-dev-projects-Resumator/3d4fe478-5da0-468a-8335-e3ee6be36201/scratchpad/`
  (`launch.py`, `shoot.mjs`, `shots/baseline/`, `shots/after-t2…t4/`; no DB copy kept, make a fresh one).
