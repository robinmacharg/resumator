# Task 2: research run PDF route

**Status:** todo. **Read:** RR1, RR3; `cv_web/server_roles.py` (`render_run`, `_get_run_document`, `_ROUTES`).

## Do

- `GET /api/roles/<id>/runs/research/<run>/research.pdf` → `render_research_pdf(run.output_md)`, cached in
  `RENDER_CACHE` (format key `research-pdf`). 409 for a run with no `output_md` (failed / dry run), 500 on render
  failure.
- Tests in `tests/test_server_roles.py` (stub the renderer).

## Done when

Route works against a DB copy for a real research run; tests pass.

## Handover

