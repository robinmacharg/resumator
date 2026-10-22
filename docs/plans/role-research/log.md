# Log: role research from the DB

- 2026-10-22 · Plan · Six tasks from the gap "Role research isn't shown" (docs/gaps.md). Decisions RR1–RR6.
- 2026-10-22 · Task 1 · `format_markdown` / `render_research_pdf` in `research_format`; file CLI output unchanged.
  Tests pass (unittest 377, npm 116).
- 2026-10-22 · Task 2 · `GET …/runs/research/<run>/research.pdf` (cached as `research-pdf`). Tests pass (unittest
  380, npm 116). Real DB: no `research_run` rows; `output/research_output.md` from 2026-08-05; formatted PDF
  rebuilt 18:02 from that old text; running server (since 15:46) has no research run in memory. So the user's
  run stored nothing: likely a file-mode run that failed or a dry run, then Format redid the old PDF.
- 2026-10-22 · Task 3 · Role mode Research tab shows the current run (`loadRoleResearch`) and its PDF; empty state
  with no role/run; failed runs keep their log; Format hidden. Tests pass (unittest 380, npm 122).
