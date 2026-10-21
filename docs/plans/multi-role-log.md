# Multi-role workspace: log

Agent log for [multi-role.md](multi-role.md), newest entry last. Append one entry per step; earlier entries
are history, not instructions.

## Log

- 2026-10-21 · Draft · Captured the multi-role idea: roles sidebar with **+**, canonical CV copy, per-run steering,
  DB exploration (leaning SQLite plus JSON), first-run import or example data or blank, PDFs on demand. Nothing
  built.
- 2026-10-21 · Refinement · User decisions R1–R6: per-role CV seeded from the master with promotion back; no
  cross-role copying; first run is example data or blank; this install migrates once via a CLI command (research
  included in the first role); CLI keeps one-shot file mode and adds `--role`/`--action`; store agent text only.
  New open questions on promote/pull merging and where the master lives.
- 2026-10-21 · Refinement · R7 (diff and merge, never overwrite), R8 (master versioned in the DB), R9 (DB at
  `cv_web/resumator.db`). Recommended one append-only `cv_version` table with `role_id NULL` for the master, rather
  than a separate table or an `is_master` flag, with a `base_master_id` as the merge ancestor. Added steps 2a and 6a.
- 2026-10-21 · Refinement · R10: the DB is the master's record and `input/CV.md` isn't re-exported (git already holds
  it). R11: merges work on whole entries and sections, built on the `cv_source` parse.
- 2026-10-21 · Refinement · R12: manual "Import `input/CV.md` as master" through the merge view, added to step 6a.
- 2026-10-21 · Design closed · R13 SQLite now; R14 role runs wrap the scripts over pipes (JSON on stdin and stdout,
  progress on stderr, no data files): user asked for pipes over files; R15 full prompt text deduplicated by hash;
  R16 PDFs warm + on demand, in a server memory cache rather than on disk (follows from R14); R17 staged
  S1–S4, roles first, merge later; R18–R20 backup command, directives per role CV, minimal role list (proposed
  defaults, not objected to). Run logs move into the DB. Steps renumbered 1–14 into stages.
- 2026-10-21 · Process · Added "Between steps": at the end of each step the agent says whether to stay or start a
  new session (based on token efficiency), plus a standard prompt to paste in.
- 2026-10-21 · Process · Created branch `feature/20261021-multi-role` from `develop` for this work.
- 2026-10-21 · Process · Added a Mermaid ER diagram beside the sketch schema; DB steps keep it current and show it inline.
- 2026-10-21 · Step 1 spike · Done; R14/R16 hold. PDF over pipes: today's `pandoc --pdf-engine=typst` command with
  stdin in and `-t pdf -o -` out gives the same page counts as the file route (default 3, compact 2) in 0.2–1 s, so
  rendering on demand is cheap. Without `-t pdf`, pandoc writes HTML. The other route (pandoc `-t typst` → `typst
  compile - -`) also works but is two processes for no gain. DOCX over stdout works, but `--reference-doc` needs a
  path, so it's built once per process in a private temp folder. `output/tailored.pdf` (4 pages, July) is stale
  against `tailored.md`. SQLite 3.54.1: `json_extract`/`json_each` read the run JSON's `metadata`, and a
  `CHECK (json_valid(...))` rejects bad JSON, so JSON columns get that check. Scripts were in the session scratchpad;
  nothing in the repo changed.
- 2026-10-21 · Step 2 store · Done. `cv_web/store.py` (stdlib `sqlite3`): `connect` (FKs, WAL, busy timeout),
  `migrate` over an append-only `MIGRATIONS` tuple, each migration in one transaction (statements split with
  `sqlite3.complete_statement`, since `executescript` commits mid-way), plus `schema_version`. CRUD for role,
  cv_version (`seed_role_cv`, base inherited from the parent), prompt_version (sha256), cv_run/research_run (JSON
  in and out, current-run switching), setting, and `backup` to `cv_web/backups/`. It differed from the sketch: CHECKs on
  status/source/kind, master rows can't have a base, failed runs can't be current, a partial unique index allows one
  current run per role, and role deletes cascade (masters are kept). Migrations are Python strings, not `.sql`
  files. 31 tests in `tests/test_store.py`; the full suite (165) passes. `.gitignore` now covers the DB and
  backups; architecture.md and AGENTS.md are updated. Open: how "archive" is stored (step 8).
- 2026-10-21 · Decision · R21: archiving a role means `status = closed`, and reopening sets the status back, so there's
  no `archived_at` column. No audit log is planned (it would be a separate table if wanted later). This closes the
  step 2 open point.
- 2026-10-21 · Step 3 merge · Done. `cv_merge.py` at the repo root (beside `cv_source.py`, not in `cv_web/`): it splits
  the raw text into units (preamble, each `#` section head, each `##` entry) using `cv_source`'s comment stripping
  and heading regexes, rather than rebuilding text from the parse dict, which would lose comments and layout.
  Untouched units round-trip byte for byte (the real `input/CV.md`, 45 units, is exact). Keys are section plus
  heading, case-insensitive, with `~~` unwrapped, so eliding an entry is a change; duplicates get `#2`. `merge` applies
  theirs onto ours: ours-only edits always survive, additions and changes are ticked by default, removals and conflicts
  need a decision (`default_accept`), and conflicts take `ours`, `theirs`, replacement text or `None`. Output order
  follows ours, so theirs' reorders are ignored. 21 tests in `tests/test_cv_merge.py`; the full suite (186) passes.
  architecture.md and AGENTS.md are updated.

- 2026-10-21 · Note · The user suggested their real CV and current PDF/DOCX outputs as baseline test material. Recorded
  in the Handoff with the current files and how to use them (read-only, skip when absent, no copied fixtures).
- 2026-10-21 · Step 4 render · Done. `cv_convert.render_cv(text, "pdf"|"docx", theme)` returns bytes over pipes, with no
  input or output files. `export_markdown` is shared with the file route, and so are `pdf_pandoc_args` and
  `docx_pandoc_args`, so both routes run the same pandoc options. The plain-pandoc PDF fallback is kept. The DOCX
  reference is built once per process in a private temp folder, removed at exit. Differed from the plan:
  `count_pdf_pages` moved from `generate_cv` to `cv_convert` and now takes bytes; `generate_cv.count_pdf_file_pages`
  wraps it for the file route. Checked against the baselines: the compact theme gives 2 pages, the same size
  (133,181 bytes) as `tailored_dev.pdf` but not byte-identical; default gives 3 pages; each render takes about
  0.2 s. The DOCX `document.xml` is identical to `tailored_dev.docx`. 10 new tests, including a parity test on the
  local `tailored.md` that skips when the file is absent; the full suite (196) passes. cv-format.md §5 and
  architecture.md are updated. Not committed.
- 2026-10-21 · Plan · Added stage S5, token efficiency (steps 15–18), as a follow-up at the user's request: measure
  usage per run, prompt caching (instructions and CV as a cacheable block), send less CV, and smaller output by
  referencing master entries. Resuming a saved model session was considered and ruled out (it saves no more than
  caching and breaks R14).
- 2026-10-21 · Process · Committed step 4 and the S5 plan addition (1678104) at the user's request.
- 2026-10-21 · Step 5 pipe mode · Done; stage S1 is complete. `generate_cv.py` and `research_role.py` take
  `--io json`. Their `main` bodies became `run_cv` and `run_research` with `files=True|False`. One-shot mode builds the
  same request from `input/` and writes the same files (smoke-checked in a scratch folder with a fake `claude`). The
  new `pipe_io.py` holds the shared harness: fd 1 points at stderr during the run, and the result goes to a copy of the
  original stdout. Bad requests and exceptions still give one JSON result. In JSON mode the PDF is rendered by
  `render_cv` into `pdf_base64`, and no DOCX is made (on demand later). `debug_log_dir` may now be None, and
  `provider_clients.attempt_log_path` / `_write_attempt_log` then log to stderr; this touched every backend's
  signature and vscodebridge's own log write. Differed from the plan: the research request also needs `jobspec` (its
  prompt uses it). `record_run_metadata` was split into a pure `cv_run_metadata`. Also fixed in passing:
  `run_claudecode_attempt` slept out the whole 15 s heartbeat even after `claude` exited, which added up to 15 s per
  real Claude run (the contract tests went from 47 s to under 5 s). 7 contract tests in `tests/test_io_json.py`; the
  full suite (203) and the frontend tests (50) pass. architecture.md, backends.md and AGENTS.md are updated.
  Committed at the user's request.
- 2026-10-21 · Step 6 role runner · Done. `cv_web/role_runner.py`: `build_cv_request` / `build_research_request` from
  the store, `run_script` (Popen from the repo root, request on stdin, stderr streamed line by line to `on_log` and
  kept as the log, stdout read whole; no or bad JSON becomes a failed result), and `run_cv` / `run_research`, which
  save the prompt (R15) and the run row. Differed from the plan: `cv_run` has no `error` column, so the error is
  appended to the saved `log` (no schema change); prompts are stripped before hashing so the hash matches what was
  sent; research URLs are de-duplicated before sending so the stored list matches. `pdf_base64` comes back in
  `RunOutcome`, never stored. A comment marks where step 15's `usage` goes. 12 tests in `tests/test_role_runner.py`
  (real scripts, temp DB, fake `claude`); the full suite (215) and the frontend tests (50) pass. architecture.md and
  AGENTS.md are updated. Committed at the user's request.
- 2026-10-21 · Step 7 migration · Built and tested; not yet run on this install (waits for the user). `cv_web/migrate_single_role.py`
  (module CLI `python3 -m cv_web.migrate_single_role`, since no `resumator` package exists before step 13). Writes
  through `store` in one transaction after reading every file first; skips an existing role; reuses an identical
  master. Decided: `prompt_hash`, provider, model and theme are NULL (`metadata` holds only company, steering,
  page count and warnings); archived runs only via `--archive`; research optional (`--no-research`). Found: the
  research output to import is a "Bridge Probe" bridge test, not Quantum Base, so the user needs to decide whether to
  import it. 8 tests in `tests/test_migrate_single_role.py`; the full suite (223) passes; a trial on the real files
  went into a scratch DB. architecture.md and AGENTS.md are updated. Not committed.
- 2026-10-21 · Process · Committed step 7 (4ef82a3) at the user's request. Split the plan at the user's request to cut
  per-session reading: `multi-role.md` (status, steps, Handoff, about 12 KB, read every session),
  `multi-role-design.md` (R1–R21, schema, run I/O, UI, first run, migration, CLI; read the sections a step needs) and
  this log (append-only; read the last few entries). Content moved unchanged apart from cross-references; the
  docstrings in `store.py`, `role_runner.py` and `migrate_single_role.py` now point at the design file.
- 2026-10-21 · Step 7 install run · The user ran the migration by hand with `--no-research`: the DB has master v1,
  role 1 "Quantum Base" (CV version 2) and 3 CV runs (3 current), and no research. Step 7 is done.
- 2026-10-21 · Step 8 server API · Done; committed at the user's request. `cv_web/server_roles.py` adds the role API (roles CRUD,
  archive via status, delete via `POST …/delete`; role and master CV read/save as `edit` versions; run list, detail,
  select current, start CV/research runs in the background through `role_runner`; run PDF/DOCX through an in-memory
  LRU `RENDER_CACHE`, warmed by a finished run). Kept additive: file-based endpoints and the UI are unchanged until
  step 9. "Scoped to a role" = role runs share the run locks and live state, so `/api/run/status` and
  `/api/research/status` carry `roleId`/`runId`. Decided: camelCase JSON; GET/POST only; documents re-rendered
  from `raw_output` validated with the run day's cutoff (no tagged markdown is stored); master CV routes added now
  for step 9. Added `CVWebHandler._bytes_response`. Fixed while testing: release the run
  lock only after finalizing; `?theme=` needs `keep_blank_values`. Known limit: research stop can't kill the
  provider child (no new session in `run_script`). 20 tests in `tests/test_server_roles.py`; the full suite (243)
  and the frontend tests (50) pass; smoke-tested over HTTP on a scratch copy of the real DB (run 3 renders, 133 KB
  compact PDF). architecture.md ("Role API"), static/ARCHITECTURE.md and AGENTS.md are updated.
- 2026-10-21 · Step 9 UI · Done (not committed); stage S2 is complete. New `role-workspace-feature.js` (sidebar,
  **+** dialog, status select = archive, delete, role switch with an unsaved-edits confirm, Role CV / Master CV
  picker, role-owned `cv`/`jobspec` editors saved through the Role API, steering debounced and theme saved on the
  role, one-time localStorage copy) and `role-runs-feature.js` (run picker, preview via `setCvRunSource` with a
  DOCX link, Tailored tab shows the run's model JSON). Hooks added to the draft, steering, theme, preview,
  pipeline, research, operations, run-state, init and bindings features; sidebar, dialog and pickers in
  `index.html`, new `styles/roles.css`. Decided: role mode = the DB has roles (else file mode until step 12);
  the selected role is remembered in localStorage, not `setting.last_role_id`; the CV and job spec are role-owned
  keys that `draft-files-feature` keeps out of file payloads, drafts and snapshots (the file endpoints write
  `input/`); the format button is hidden in role mode (a theme change re-renders on demand); role runs save dirty
  role editors, steering and prompt files first, and send the steering as shown. Research runs go to the role
  API, but past role research and its PDF aren't shown (gap logged in gaps.md: needs a research render route).
  No "make current" button (the API has it). 28 new frontend tests (78 total) and the Python suite (243) pass. A
  headless-Chrome CDP smoke test on a scratch DB copy (port 8799) covered boot, master toggle, save (new `edit`
  version, `input/CV.md` untouched), theme, run picker, steering, create, archive, delete and reload. Not run: a
  real role CV or research run from the UI (model call). Docs: static/ARCHITECTURE.md, architecture.md, gaps.md,
  cv-format.md.
- 2026-10-21 · Process · Committed step 9 at the user's request ("multi-role step 9"); `input/jobspec.txt` left out.
- 2026-10-21 · Step 10 · Done. `cv_web/role_merge.py` (`view`, `parse_decisions`, `apply`) and
  `GET/POST /api/roles/<id>/merge` in `server_roles`; `role-merge-feature.js` with Promote/Pull buttons beside the CV
  picker and a merge dialog (checkbox per change, removals unticked, inline diff, conflicts highlighted with keep /
  take / edit, all required; refused while the CV editor is dirty; 409 if either CV changed since the view).
  Decided: a pull sets the role's base to the current master (also when nothing merges but the master moved on);
  a promote moves the base (via an unchanged-content `promote` role version) only when nothing is left to pull,
  else unpulled master changes would look like role reverts. Edited conflict text left blank drops the entry. Fixed
  during the check: the global dark `pre` style made the diff highlights unreadable (own light style now). 13 new
  Python tests (256) and 5 frontend (83) pass. A headless-Chrome CDP smoke test on a scratch DB copy (port 8799)
  with synthetic edits covered pull (conflict refused until resolved, applied), promote (removal unticked, master
  kept it, base moved) and the dirty-editor refusal; `input/CV.md` unchanged. Docs: architecture.md, static
  ARCHITECTURE.md, gaps.md (merge limits), design doc (base rule), AGENTS.md.
- 2026-10-21 · Process · Committed step 10 at the user's request ("multi-role step 10"); `input/jobspec.txt` left out.
- 2026-10-21 · Step 11 · Done. Version history: `GET …/cv/versions/<v>` and `POST …/restore` for
  role and master CVs (restore = a new `edit` version, "Restored version N"), with `cv-history-feature.js` (History
  button; works for whichever CV is open, a small widening of the step's "master" scope). Import (R12):
  `role_merge.import_view`/`apply_import`, `GET/POST /api/master/import`, the merge dialog's `import` mode, and an
  Import CV.md button shown only with the master open. Differed from the design: the base isn't "the master version
  last imported from" (a test showed a merged import version makes master-only edits look like file reverts,
  ticked by default); it's the file text at the last import in `setting.master_import_text`, falling back to the
  newest `import` version, else empty. Declined file changes don't come back. Fixed during the check: a global
  `pre` max-height clipped the history text. 6 new Python tests (262) and 4 frontend (87) pass. A CDP smoke test on
  a fresh scratch DB copy with an edited scratch `CV.md` covered the button visibility, import, "nothing left to
  import", history and restore; `input/CV.md` unchanged. The live DB has the user's own promote trials (20:36 UTC,
  roles 2–3), checked to be theirs, not test writes. Docs: architecture.md, static ARCHITECTURE.md, gaps.md, design doc.
- 2026-10-21 · Process · Committed step 11 at the user's request ("multi-role step 11"); `input/jobspec.txt` left out.
- 2026-10-21 · Step 12 · Done. `cv_web/first_run.py` (`status`, `set_up`) and `GET/POST /api/setup`; fictional
  `examples/` (master CV, job spec, canned run with a fixed date, blank TODO template; both CVs lint clean). The UI
  asks on a new install (`#firstRunDialog`, example or blank). Differed from the plan: with no roles the UI stays in
  role mode with only the master open (`state.workspace` apart from `activeRoleId`, `body.no-role`,
  `[data-needs-role]`; runs refused, job spec read-only, preview says "No role yet") instead of falling back to file
  mode, which is now only for an unreachable role API. Both master versions use source `example`. Fixed during the
  check: Chrome let Escape close the dialog (the `cancel` isn't cancellable without user activation), so it reopens
  on close; the no-role preview said "No runs yet for this role" (run sources can carry a placeholder now). 12 new
  Python tests (274) and 7 frontend (94) pass. A CDP smoke test on fresh scratch DBs (port 8799) covered example
  (role, canned run, its PDF 200, no dialog after reload) and blank (Escape, master-only controls, run refused,
  creating a role leaves no-role mode); `input/CV.md` unchanged. Docs: architecture.md, static ARCHITECTURE.md,
  gaps.md, design doc, AGENTS.md. Committed as "multi-role step 12"; `input/jobspec.txt` left out.
