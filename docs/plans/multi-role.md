# Plan: multi-role workspace

**Goal:** keep several job applications ("roles") side by side. Each role has its own job spec, steering, CV runs and
research runs. A sidebar lists the roles, with a **+** to create one, and a new role can start from a copy of the
canonical master CV. Storage moves to a small database. Only agent-returned text is stored; PDFs are rendered on
demand.

**Status:** IN PROGRESS. Design agreed (R1–R21). Stage S1 (steps 1–5) done: spike, `cv_web/store.py`, `cv_merge.py`,
`cv_convert.render_cv`, `--io json` pipe mode. S2 step 6 (`cv_web/role_runner.py`) done. Step 7 (migration command) built and
tested; running it on this install waits for the user's go-ahead. Then step 8, the server API.
Work happens on branch `feature/20261021-multi-role` (from `develop`).

**Files:** this one holds the status, steps and Handoff (read it every session). The design (decisions R1–R21,
schema, run I/O, UI, first run, migration, CLI) is in [multi-role-design.md](multi-role-design.md): read only the
sections the current step needs. The Log is in [multi-role-log.md](multi-role-log.md): append one entry per step;
read only its last few entries.

## Stages and steps

Each stage ends with the app working and tests passing. One-shot CLI behaviour is unchanged throughout.

**S1 — Foundations** (no visible change to the UI)

| # | Step | Output | Status |
|---|---|---|---|
| 1 | Spike: `pandoc` → `typst` over stdin/stdout with a theme (`--root`), PDF bytes and page count, and timing; SQLite JSON functions over the current `tailored.model.json`. Confirm or adjust R14/R16 | Spike notes in the log | done |
| 2 | `store.py`: connect, migrations (`schema_version`), CRUD for role, cv_version, prompt_version, cv_run, research_run, setting; `backup` (R18). Tests on a temp DB | Data layer | done |
| 3 | `cv_merge.py`: entry-level three-way merge on `cv_source` parses (R11), rebuilding the CV text. Tests | Merge engine (not wired yet) | done |
| 4 | In-memory render function in `cv_convert` (markdown + theme → PDF/DOCX bytes) | Render without files | done |
| 5 | `--io json` mode for `generate_cv` and `research_role` (R14). Contract tests: request in, result out, nothing written to `input/` or `output/` | Pipe mode | done |

**S2 — Usable roles** (side-by-side applications)

| # | Step | Output | Status |
|---|---|---|---|
| 6 | `role_runner.py`: request from DB → script → result → run row, prompt saved (R15), log saved | Runs persisted | done |
| 7 | Migration command (R4); run it on this install: master v1 from `input/CV.md`, Quantum Base role, current and archived CV runs, current research | Migrated | built; install run pending |
| 8 | Server API: `/api/roles` (list, create, update, archive = status `closed` (R21), delete), `/api/roles/<id>/cv` (read, save as a new version), runs (list, select current, start), PDF/DOCX of a run and theme through the memory cache (R16); existing endpoints scoped to a role | API | todo |
| 9 | UI: sidebar with **+**, role switching, CV tab edits the role CV, master opened and edited directly (no merge yet), steering and theme per role (one-time copy from localStorage), run-history picker | Roles usable | todo |

**S3 — Master versions and merge**

| # | Step | Output | Status |
|---|---|---|---|
| 10 | Promote and pull: merge view (one checkbox per entry, removals unticked by default, conflicts highlighted, inline `difflib` diff) over the S1 engine (R7, R11) | Two-way sync | todo |
| 11 | Master version history (view and restore as a new version) and "Import `input/CV.md` as master" (R12) | History and import | todo |

**S4 — Finish**

| # | Step | Output | Status |
|---|---|---|---|
| 12 | First-run flow: example data or blank (R3) | First run | todo |
| 13 | Role-mode CLI: `python3 -m resumator --role … --action cv|research|render|list|create|backup` | CLI | todo |
| 14 | Docs: architecture, cv-format, AGENTS.md, gaps; retire the single-file assumptions | Docs in sync | todo |

**S5 — Token efficiency** (follow-up; measure first, then act on what the numbers show)

Rough per-run split today (about 4 characters per token, unmeasured): instructions about 2.4k and master CV about 6k
(both stable), job spec, run facts and steering about 1–1.5k (vary), and output JSON about 3.5–4k (costs about 5× input).
`build_prompt` already puts the stable parts first. Ruled out: resuming a saved model session with the CV preloaded. It
still bills the whole history as cached input (the same saving as caching), risks leaking one role into another,
expires, and breaks stateless pipe runs (R14).

| # | Step | Output | Status |
|---|---|---|---|
| 15 | Record token usage per run: input, cached input, output (the `claude -p` JSON has `usage`; the OpenAI/Gemini APIs return it too). New `store.MIGRATIONS` entry (`usage_json` on `cv_run` and `research_run`) and a field in the `--io json` result; shown with the run | Real numbers | todo |
| 16 | Prompt caching: send the instructions and master CV as their own cacheable block (Anthropic: a `cache_control` block, or the system prompt for `claude -p`) and the job spec, facts and steering after it. Confirm OpenAI and Gemini prefix caching hits by using step 15. Check provider docs for TTL and minimum sizes first | Cheaper re-runs (estimate 25–30%) | todo |
| 17 | Send less: drop elided and `omit` entries and roles past the cutoff before sending (check what's already dropped), and condense earlier-career roles to one line | Smaller input | todo |
| 18 | Smaller output (contract change: prompt, validator, `render_tagged_markdown`, `cv_convert` together): mostly-copied sections (education, earlier career, skills) come back as references to master entries, and the tool fills in the text. Optionally a "regenerate these sections only" run for steering-only changes | Smaller output, the biggest saving | todo |

## Between steps: stay or start a new session

At the end of every step, the agent updates the step's status, the Log (multi-role-log.md) and the Handoff, then tells the user one of
the following, with a one-line reason:

- **Start a new session** when any of these is true: the context is past about half full; the step loaded a lot
  that the next step won't need (spike output, long test runs, large files); the next step works on different
  files; or a stage has just finished. A fresh session reloading the plan costs less than carrying a full context.
- **Stay in this session** when the context is still small and the next step mainly uses files this step read or
  wrote, so reloading them would cost more than keeping them.

Expected pairs where staying usually pays: 4 → 5 (the render function feeds pipe mode) and 10 → 11 (same merge
view). Start fresh at every stage boundary (after steps 5, 9, 11, 14) and after the step 1 spike.

Paste this to start or continue either way:

```text
Continue the multi-role plan in docs/plans/multi-role.md on branch feature/20261021-multi-role (check it's
checked out first). Read its Handoff and the last few entries of docs/plans/multi-role-log.md, then do the
next todo step only, following AGENTS.md. At the end: mark the step's status, add a Log line and update the
Handoff, then tell me whether to stay in this session or start a new one for the next step, and why.
```

## Open questions

None blocking. Step 1 (the spike) may reopen R14/R16 if Typst can't render from stdin with theme imports, or if
in-memory rendering is too slow; the fallback is a private temp directory per render, deleted afterwards.

## Handoff

For the next session: the design is agreed (R1–R21) and stage S1 is done. Work on branch `feature/20261021-multi-role`.
Steps 1–6 are committed (4 in 1678104; 5 and 6 in the "multi-role step 5" and "step 6" commits). The Schema section in multi-role-design.md is what's built.
`input/jobspec.txt` has an unrelated uncommitted change of the user's: leave it out of commits.
Step 5 gave `python3 generate_cv.py --io json` and `python3 research_role.py --io json` ("Run I/O" in the design file has the exact
shapes, and `generate_cv.new_cv_result` is the CV result). Both share `pipe_io.run_json_io` (fd 1 → stderr during the
run). The pipelines are now `generate_cv.run_cv(request, files=…)` and `research_role.run_research(request, files=…)`,
and one-shot mode builds the same request from `input/`. `debug_log_dir=None` sends provider attempt logs to stderr.
Contract tests are in `tests/test_io_json.py`: real subprocesses from an empty temp cwd, with a fake `claude` on PATH.
Step 6 gave `cv_web/role_runner.py`: `run_cv(conn, role_id, …)` and `run_research(conn, role_id, …)` build the
request from the store (`build_cv_request` / `build_research_request`; `theme`/`steering`/`company` None = the role's,
"" = none; `prompt` None = the template file), save the prompt (R15), run the script via `run_script` (stderr lines
to `on_log`, the process to `on_start` for cancelling, `env` for tests) and save the run row. They return a
`RunOutcome` (`run_id`, `success`, `error`, `log`, `result`, `pdf_base64`). Errors are appended to the run's `log`
as `[runner] error: …` (no `error` column). `RunnerError` means nothing ran or was saved. Tests:
`tests/test_role_runner.py`. Nothing calls it yet (server: step 8; CLI: step 13).
Step 7 gave `cv_web/migrate_single_role.py` (`migrate_single_role(conn, name, …)` → `MigrationReport`; CLI
`python3 -m cv_web.migrate_single_role --name … [--company] [--archive DIR]… [--no-research] [--db]`). All files are
read before one transaction; it skips when the role exists and reuses the master when `input/CV.md` is identical.
Provider, model, theme and `prompt_hash` stay NULL (not in the files); all runs point at the seeded CV version; file
mtimes are the run times. Tests: `tests/test_migrate_single_role.py`. A trial on the real files into a scratch DB
gave master v1, the role, 3 CV runs (step8, step9, current = current) and 1 research run.
**Pending before step 8:** run it on this install (`cv_web/resumator.db` doesn't exist yet) once the user says go,
and settle the research import: `output/research_output.json` is a "Bridge Probe" / `https://example.com`
vscodebridge test from 5 Aug, not Quantum Base research, so `--no-research` may be right. Suggested command:
`python3 -m cv_web.migrate_single_role --name "Quantum Base" --archive output/step8-opus-fastmode --archive
output/step9-opus [--no-research]`. `output/baseline-gemini-2.5-flash/` has no `tailored.model-output.txt`, so it
can't be imported as a run.
Next is step 8: the server API (see the steps table).
Baseline test material (user's suggestion): `input/CV.md` and the current outputs `output/tailored.md`,
`tailored.model.json`, `tailored_dev.pdf` and `tailored_dev.docx` (21 Oct; `tailored.pdf`/`.docx` from July are stale).
Use them read-only for local checks, and in tests only with a skip when they're absent (`output/` is gitignored and the
CV is real), without copying their content into committed fixtures. `tailored_dev.pdf` was rendered with the
`compact` theme.
For step 10: `cv_merge.merge(base, ours, theirs, accept, resolutions)`; promote is ours = master, theirs = role,
pull is ours = role, theirs = master, base = the role's `base_master_id` version. Archiving is `status = closed` (R21),
so step 8 needs no schema change for it.
Schema changes go in a new `store.MIGRATIONS` entry; never edit migration 1. Keep the diagram and SQL in step. Each
stage should leave the app working. S5 (steps 15–18, token efficiency) is a follow-up after S4. The related work is in
[cv-format-revamp.md](cv-format-revamp.md) (steering D11/D23, theme picker, run metadata).
