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
- 2026-10-22 · Task 4 · Research run picker (make current, reload) and company/URL prefill from the current run.
  Checked in headless Chrome on a DB copy. Tests pass (unittest 380, npm 128). User's "404 - unknown route" not
  reproduced; likely a stale server or page.
- 2026-10-22 · Task 5 · `research --out F` and `render --kind research [--run N]` write a research run's PDF.
  Checked on a DB copy. Tests pass (unittest 384, npm 128).
- 2026-10-22 · Task 6 · Docs updated (architecture, gaps, TODO, AGENTS test list); one CLI refusal test added. Plan
  done. Tests pass (unittest 384, npm 128).
