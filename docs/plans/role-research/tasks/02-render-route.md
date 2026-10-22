# Task 2: research run PDF route

**Status:** done. **Read:** RR1, RR3; `cv_web/server_roles.py` (`render_run`, `_get_run_document`, `_ROUTES`).

## Do

- `GET /api/roles/<id>/runs/research/<run>/research.pdf` → `render_research_pdf(run.output_md)`, cached in
  `RENDER_CACHE` (format key `research-pdf`). 409 for a run with no `output_md` (failed / dry run), 500 on render
  failure.
- Tests in `tests/test_server_roles.py` (stub the renderer).

## Done when

Route works against a DB copy for a real research run; tests pass.

## Handover

- `server_roles.render_research_run(conn, run)` + `_get_research_document`; route `get_research_document`.
  Cache key `(run id, "", RESEARCH_PDF_FORMAT)` with `RESEARCH_PDF_FORMAT = "research-pdf"` (ids overlap CV runs).
  Heading is `research_format.DEFAULT_HEADING`. Filename `<slug>-research<id>.pdf`. 409: failed run or blank
  `output_md` (covers dry runs); 500: `RuntimeError` from the renderer.
- Tests: `ResearchDocumentTests` in `tests/test_server_roles.py`. On a DB copy, August's research text stored as a
  run rendered to the same byte size as `output/research_output.formatted.pdf`.
- Finding: the user's real DB has **no** `research_run` rows and `output/research_output.md` dates from 2026-08-05,
  so the run the user saw saved nothing in either place (see log). Task 3 should make failures visible.
