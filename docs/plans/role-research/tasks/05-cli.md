# Task 5: role CLI research PDF

**Status:** done. **Read:** RR6; `resumator.py` (`_cv`, `_research`, `_render`).

## Do

- `--action research --out F` writes the run's PDF.
- `--action render --kind research [--run N]` renders the current or given research run (default
  `output/<slug>-research<id>.pdf`); `--kind` defaults to `cv`.
- Tests in `tests/test_resumator_cli.py`.

## Done when

Both work on a DB copy; tests pass.

## Handover

- `_research_pdf(conn, run)` (shared by `research --out` and `_render_research`) calls
  `research_format.render_research_pdf` with `settings_env.effective_env`; no render cache in the CLI. Refuses a
  failed run or blank `output_md` (says "(dry run)" for dry runs), `--format docx` and `--theme`.
- Tests: four in `RunTests` (`tests/test_resumator_cli.py`), renderer patched. On a DB copy both `render --kind
  research` forms wrote real PDFs. `research --out` with a real model call not run (mocked only).
- The real DB now has a research run (id 1), unlike at task 2.
- `docs/architecture.md` `resumator.py` row updated; the rest of the docs are task 6.
