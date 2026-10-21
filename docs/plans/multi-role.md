# Plan: multi-role workspace

**Goal:** keep several job applications ("roles") side by side. Each role has its own job spec, steering, CV runs and
research runs. A sidebar lists the roles, with a **+** to create one, and a new role can start from a copy of the
canonical master CV. Storage moves to a small database. Only agent-returned text is stored; PDFs are rendered on
demand.

**Status:** IN PROGRESS. Design agreed (R1–R21). Stage S1 (steps 1–5) done: spike, `cv_web/store.py`, `cv_merge.py`,
`cv_convert.render_cv`, `--io json` pipe mode. S2 steps 6–8 done: `cv_web/role_runner.py`, the migration (run on this
install), and the role API (`cv_web/server_roles.py`). Next is step 9, the UI, which ends S2.
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
| 7 | Migration command (R4); run it on this install: master v1 from `input/CV.md`, Quantum Base role, current and archived CV runs, current research | Migrated | done |
| 8 | Server API: `/api/roles` (list, create, update, archive = status `closed` (R21), delete), `/api/roles/<id>/cv` (read, save as a new version), runs (list, select current, start), PDF/DOCX of a run and theme through the memory cache (R16); existing endpoints scoped to a role | API | done |
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

For the next session: the design is agreed (R1–R21). S1 and S2 steps 6–8 are done; step 9 (the UI) finishes S2. Work on
branch `feature/20261021-multi-role`. Steps 1–8 are committed (step 8 in "multi-role step 8").
`input/jobspec.txt` has an unrelated uncommitted change of the user's: leave it out of commits.
The Schema section in multi-role-design.md is what's built.

**This install's DB** (`cv_web/resumator.db`, gitignored) was migrated by the user: master v1 (`import`), role 1
"Quantum Base" (slug `quantum-base`, its CV is version 2, `seed`), 3 CV runs (ids 1–2 archived, 3 current, all
with NULL provider/model/theme/prompt hash) and no research (`--no-research`). Don't write to it in checks: copy it
with SQLite's backup API into the scratchpad and point `server_roles.DB_PATH` at the copy.

**Step 8 gave the role API**, `cv_web/server_roles.py` (`dispatch(handler, method, parsed, payload, deps)`, tried by
`server_http_handlers.dispatch_get/post` before their 404; returns False for routes it doesn't own). Routes and JSON
shapes: docs/architecture.md, "Role API". Key points for step 9:
- camelCase keys everywhere (`camel(row)`); role fields in: `name, slug, company, status, jobspec, steeringText,
  steeringEnabled, theme`. Create seeds the CV from the master. Archive = update `{status: "closed"}`. Delete is
  `POST …/delete` (the API is GET/POST only, like the rest).
- CV save: `POST /api/roles/<id>/cv` or `/api/master/cv` with `{content, note}` adds an `edit` version, or returns
  `unchanged: true`. Responses carry `{cv, versions}`.
- Runs: `POST /api/roles/<id>/runs/cv` `{selectedProvider, selectedModel, theme, steering}` (null = the role's) and
  `…/runs/research` `{…, company, urls, dryRun}`. They share `RUN_LOCK`/`RESEARCH_RUN_LOCK` and the live state, so
  the UI keeps polling `/api/run/status` / `/api/research/status`. Those carry `kind: "role-cv"` and `roleId`, and
  `runId` and `error` once finished. That is how the existing endpoints are scoped to a role.
- PDF/DOCX: `GET /api/roles/<id>/runs/cv/<run>/cv.pdf?theme=` (no `theme` = the run's; empty = default). They're
  re-rendered from `raw_output` (`run_markdown`: validated with the run day's cutoff, plus the CV version's
  directives) through `RENDER_CACHE` (LRU, 32). A finished run warms its own PDF. Measured on run 3: about 0.2–1.2 s
  cold, 1 ms cached.
- The file-based endpoints (`/api/state`, `/api/save`, `/api/run/full|format`, research) are unchanged, and today's
  UI still uses them. In step 9 the CV and job spec editors, steering and theme move to the role; the prompt and
  `.env` editors stay file-based. The steering/theme localStorage copy happens once (see the steps table).
- Known limit: `role_runner.run_script` doesn't start a new process session, so research stop
  (`request_stop_research_run`) falls back to `terminate()` of the script; a provider child process may outlive it.
  Fix there (`start_new_session=True`) if stop matters; mind Ctrl-C for the step 13 CLI.
- `setting.last_role_id` isn't written by the API yet. Step 9 decides where the selected role is remembered.
Tests: `tests/test_server_roles.py` (20; temp DB, `render_cv` and `role_runner.run_cv/run_research` patched).

Baseline test material (user's suggestion): `input/CV.md` and the current outputs `output/tailored.md`,
`tailored.model.json`, `tailored_dev.pdf` and `tailored_dev.docx` (21 Oct; `tailored.pdf`/`.docx` from July are stale).
Use them read-only for local checks, and in tests only with a skip when they're absent (`output/` is gitignored and the
CV is real), without copying their content into committed fixtures. `tailored_dev.pdf` was rendered with the
`compact` theme.
For step 10: `cv_merge.merge(base, ours, theirs, accept, resolutions)`; promote is ours = master, theirs = role,
pull is ours = role, theirs = master, base = the role's `base_master_id` version.
Schema changes go in a new `store.MIGRATIONS` entry; never edit migration 1. Keep the diagram and SQL in step. Each
stage should leave the app working. S5 (steps 15–18, token efficiency) is a follow-up after S4. The related work is in
[cv-format-revamp.md](cv-format-revamp.md) (steering D11/D23, theme picker, run metadata).
