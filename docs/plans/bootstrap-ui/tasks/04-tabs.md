# Task 4: tabs and sub-tabs

**Status:** todo. **Read:** [design § Class mapping](../design.md#class-mapping), B2.

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

(empty)
