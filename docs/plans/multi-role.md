# Plan: multi-role workspace

**Goal:** keep several job applications ("roles") side by side. Each role has its own job spec, steering, CV runs and
research runs. A sidebar lists the roles, with a **+** to create one, and a new role can start from a copy of the
canonical master CV. Storage moves to a small database. Only agent-returned text is stored; PDFs are rendered on
demand.

**Status:** IN PROGRESS. Design agreed (R1–R21). Stage S1 (steps 1–5) done: spike, `cv_web/store.py`, `cv_merge.py`,
`cv_convert.render_cv`, `--io json` pipe mode. S2 steps 6–8 done: `cv_web/role_runner.py`, the migration (run on this
install), and the role API (`cv_web/server_roles.py`). Step 9 (the UI) is done, so S2 is complete. S3 (steps 10–11:
promote and pull, version history and import) is done. S4 (steps 12–14: first-run flow, role-mode CLI, docs) is done, so the
multi-role build is complete. S5 (steps 15–18, token efficiency) is the follow-up.
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
| 9 | UI: sidebar with **+**, role switching, CV tab edits the role CV, master opened and edited directly (no merge yet), steering and theme per role (one-time copy from localStorage), run-history picker | Roles usable | done |

**S3 — Master versions and merge**

| # | Step | Output | Status |
|---|---|---|---|
| 10 | Promote and pull: merge view (one checkbox per entry, removals unticked by default, conflicts highlighted, inline `difflib` diff) over the S1 engine (R7, R11) | Two-way sync | done |
| 11 | Master version history (view and restore as a new version) and "Import `input/CV.md` as master" (R12) | History and import | done |

**S4 — Finish**

| # | Step | Output | Status |
|---|---|---|---|
| 12 | First-run flow: example data or blank (R3) | First run | done |
| 13 | Role-mode CLI: `python3 -m resumator --role … --action cv|research|render|list|create|backup` | CLI | done |
| 14 | Docs: architecture, cv-format, AGENTS.md, gaps; retire the single-file assumptions | Docs in sync | done |

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

For the next session: the design is agreed (R1–R21). Steps 1–14 are done (S1–S4 complete); next is S5, step 15
(record token usage per run), a follow-up the user may schedule separately. Work on branch
`feature/20261021-multi-role`. Steps 1–14 are committed (step 14 in "multi-role step 14"); the branch hasn't been
merged or pushed. `input/jobspec.txt` has an unrelated uncommitted
change of the user's: leave it out of commits. The Schema section in multi-role-design.md is what's built.

**This install's DB** (`cv_web/resumator.db`, gitignored) was migrated by the user: master v1 (`import`), role 1
"Quantum Base" (slug `quantum-base`, its CV is version 2, `seed`), 3 CV runs (ids 1–2 archived, 3 current, all
with NULL provider/model/theme/prompt hash) and no research (`--no-research`). Don't write to it in checks: copy it
with SQLite's backup API into the scratchpad and point `server_roles.DB_PATH` at the copy. The user's own server
may be running on 8765; smoke-test on another port by setting `server.PORT` before `server.run_server()`.
Headless Chrome (`/Applications/Google Chrome.app`) with `--remote-debugging-port` plus Node 24's built-in
`WebSocket` drives the UI over CDP well (step 9 log entry).

**The Role API** is in `cv_web/server_roles.py`; routes and JSON shapes are in docs/architecture.md, "Role API"
(camelCase keys; GET/POST only; CV saves are `POST …/cv` `{content, note}` → an `edit` version or `unchanged`).

**Step 9 gave the role UI** (cv_web/static/ARCHITECTURE.md has the module notes). Key points for step 10:
- `role-workspace-feature.js` owns the CV editor in role mode. `state.cvSource` is `"role"` or `"master"`
  (`cvSourceSelect`), `loadOpenCv` loads it, `saveFile("cv")` saves the open one, and `applyRoleFiles({cv})` sets
  the editor and the saved snapshot. The CV tab label (`editableFiles.cv.tabLabel`) says which CV is open.
  Promote and Pull buttons belong in the CV editor head beside `cvSourceSelect` (`data-role-only`); after a merge
  is saved, reload the open CV with `loadOpenCv` / `applyRoleFiles`.
- Unsaved edits: `hasUnsavedEdits()` / `confirmDiscard`. Save or refuse before opening a merge view.
- Run-time disabling is `run-state-feature.applyControlDisabledState` (the sidebar is a `<fieldset>`); add new
  role controls there.
- The merge view needs new API routes (none exist yet): for example `GET …/merge?direction=promote|pull` returning
  the `cv_merge` entries and conflicts, and `POST` with `accept`/`resolutions`. The role CV row has
  `base_master_id`. Promote and pull add versions with sources `promote`/`pull` (check `store` for the allowed
  `source` values and how `base_master_id` moves).
- Known UI limits: no "make current" run button (the API has `…/current`); past role research runs and the
  research PDF aren't shown (docs/gaps.md). (File mode for an empty DB was replaced in step 12.)
- Known backend limit (from step 8): `role_runner.run_script` doesn't start a new process session, so research stop
  falls back to `terminate()` of the script; a provider child may outlive it. Mind Ctrl-C for the step 13 CLI.

**Step 14 brought the docs in line** (README, architecture.md "two ways to run" and file contract, cv-format.md,
gaps.md, AGENTS.md, static ARCHITECTURE.md). Known gaps left for later are in docs/gaps.md: role research output
and PDF still file-based, past run logs not shown, UI file-mode fallback to remove, merge limits.

**Step 13 gave the role CLI** (`resumator.py`, design doc "CLI (R5)" as built; docs/architecture.md row). For
step 14: AGENTS.md and architecture.md already list it; README/docs that still describe only the file-based flow
are the work. `role_runner.run_markdown` now holds run rendering (server_roles wraps it as 409s). Ctrl-C: provider
groups are tracked in `provider_clients` and killed at exit, and `pipe_io` turns SIGTERM into a normal exit, so the
step 8 "research stop leaves the provider running" limit is probably fixed for role runs too, but the server stop
path wasn't re-tested.

**Step 12 gave the first run** (design doc "First-run behaviour", as built): `cv_web/first_run.py` (`status`,
`set_up`) over `examples/`, routes `GET/POST /api/setup`. The UI has `state.workspace` (role mode, DB in use) apart
from `activeRoleId`; with no roles only the master is open (`isMasterOnly`, `body.no-role`, `[data-needs-role]`).
Example data is handy for tests: `first_run.set_up(conn, "example")` gives a role with a current run. For step
14: file mode in the UI is now only a fallback when the role API fails; the one-shot CLI is still file-based (R5).

**Steps 10–11 gave promote, pull, import and history** (docs/architecture.md "Role API", static/ARCHITECTURE.md).
Step 11 as built: `cv-history-feature.js` (History button, role or master CV, restore = a new `edit` version via
`…/cv/versions/<v>/restore`) and import through the merge dialog (`GET/POST /api/master/import`, Import CV.md button
shown only with the master open). The import base is the file text at the last import in `setting.master_import_text`
(design doc, "CV versions").
Step 10 notes, kept for reference:
- `cv_web/role_merge.py`: `view(conn, role_id, direction)` / `parse_decisions` / `apply(…)` over `cv_merge`. Routes
  `GET/POST /api/roles/<id>/merge`. The base rule (pull moves it, promote only when nothing is left to pull) is in
  the design doc's "CV versions" section.
- `role-merge-feature.js` owns the dialog (`#mergeDialog`, reusing `.role-dialog`); `openMerge(direction)`,
  `applyMerge`, `closeMerge`. Its rendering (checkbox or conflict radios + diff per change) takes a view shaped
  like the merge GET. R12's import can reuse it: build the same view with base = the master version last imported
  (`source = import`), ours = master, theirs = `input/CV.md`, saved as an `import` master version. A small
  generalisation (a view loader and save path per mode) is enough; keep the role-only refusals.
- Version history needs a content route (none yet: `…/cv` lists versions without content); restoring = a new
  version (`edit`, or add a note) per R8.
- Known merge limits are in docs/gaps.md ("Merge limits").
- Local checks used a scratch DB copy with synthetic edits (role 1 on this install is still the unedited seed, so
  real views are empty).
Baseline test material (user's suggestion): `input/CV.md` and the current outputs `output/tailored.md`,
`tailored.model.json`, `tailored_dev.pdf` and `tailored_dev.docx` (21 Oct; `tailored.pdf`/`.docx` from July are stale).
Use them read-only for local checks, and in tests only with a skip when they're absent (`output/` is gitignored and the
CV is real), without copying their content into committed fixtures.
Schema changes go in a new `store.MIGRATIONS` entry; never edit migration 1. Keep the ER diagram in [docs/db-schema.md](../db-schema.md) in step. Each
stage should leave the app working. S5 (steps 15–18, token efficiency) is a follow-up after S4. The related work is in
[cv-format-revamp.md](cv-format-revamp.md) (steering D11/D23, theme picker, run metadata).
