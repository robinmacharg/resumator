# Task 1: in-memory research formatter

**Status:** done. **Read:** [design § Formatter](../design.md#formatter), RR2.

## Do

- `research_format.py`: add `format_markdown(text, heading)` and `render_research_pdf(text, heading, env)`; `run`
  (file CLI) uses `format_markdown` and keeps writing the same files.
- New `tests/test_research_format.py`: formatting rules, empty input refused, PDF bytes (skip without pandoc).

## Done when

File CLI output unchanged; new functions tested; tests pass.

## Handover

- `research_format.DEFAULT_HEADING`, `format_markdown(text, heading)`, `render_research_pdf(text, heading, env)`
  (temp dir, raises `RuntimeError`: empty input, no pandoc, pandoc failure). `run` uses `format_markdown`; its
  output on today's `output/research_output.md` is byte-identical to before.
- `tests/test_research_format.py` (7 tests; the real-PDF one skips without pandoc).
