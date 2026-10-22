# Bootstrap UI: log

Agent log for [index.md](index.md), newest entry last. Append one entry per task; earlier entries are history,
not instructions.

## Log

- 2026-10-22 · Design · Move the UI to Bootstrap 5.3, CSS only. User decisions: 2–4px corners (B4), Bootstrap's
  default font, Avenir dropped (B5), very pale blue background (B6), plan paperwork on a separate branch. Proposed
  and accepted with the plan: vendored CSS, no Bootstrap JS, one theme file, per-area migration (B1–B3, B7–B9).
- 2026-10-22 · Task 1 · Vendored Bootstrap 5.3.8 (SRI sha384-sRIl4kxI…ZqJLB, matches published), added
  `theme.css` (B4–B8) and token swaps; Reboot needed only heading weight, control font-size and sidebar select
  fixes. Baseline/after screenshots compared; tests pass (npm 113, unittest 370). B7 pending user confirmation.
- 2026-10-22 · B7 · User chose a medium blue: primary is Bootstrap's default `#0d6efd`; teal overrides removed
  from `theme.css`, `--brand-strong` mapped to `--brand`.
- 2026-10-22 · Task 2 · Buttons on Bootstrap: secondary → `btn-outline-secondary`, toolbars and Settings rows
  `btn-sm`, Delete role `btn-outline-danger`; our `.btn*` rules deleted, density and danger red set in `theme.css`.
  Screenshots compared (CV, Research, merge, Settings); tests pass (npm 116, unittest 370).
