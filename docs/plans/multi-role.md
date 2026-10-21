# Plan: multi-role workspace (TODO — draft for refinement)

**Goal:** keep several job applications ("roles") side by side. Each role has its own job spec, steering, CV runs and
research runs. A sidebar lists the roles, with a **+** to create one, and a new role can start from a copy of the
canonical master CV. Storage moves to a small database. Only agent-returned text is stored; PDFs are rendered on
demand.

**Status:** TODO. Draft only: nothing built. R1–R12 decided; the remaining open questions come before step 1.

## Decisions

| # | Decision | Why |
|---|---|---|
| R1 | **Every role has its own CV, seeded from the master** when the role is created, then freely editable (for example to remove a previous employer or sensitive details). A role can **promote** its CV (or edits) to the master at any time, so edits can flow both ways | Your call. The master stays the best "everything" record; roles tailor what's disclosed |
| R2 | **No cross-role copying** for now; copy and paste covers it | Your call. Keeps the model simple |
| R3 | **First run** for a new user: example data or blank. No general "import existing" option | Your call. Most users have no single-role history to bring over |
| R4 | **One-time migration for the current install** (a CLI command, not a UI path): today's files become the first role, including the current research output | Your call. It's a one-off move from single-role to multi-role |
| R5 | **CLI keeps today's one-shot, file-based generation** and adds role mode: `--role "Name" --action cv|research|…` | Your call. Scripting and quick runs stay possible without the DB |
| R6 | **Only agent-returned text is stored**; PDFs are rendered on demand | Your call (original brief) |
| R7 | **Changes between master and role CVs are diffed and merged, never overwritten.** Information removed from a role stays in the master | Your call. A role's deliberate removals must not delete facts from the master |
| R8 | **The master CV is versioned in the DB**, alongside the role CVs: every save, promotion or merge adds a version with its date and source | Your call. Gives history, undo, and the common ancestor that merges need |
| R9 | **The DB sits beside the main server file:** `cv_web/resumator.db`, gitignored | Your call, "for now". Easy to move later behind one path constant |
| R10 | **The DB is the master's record; `input/CV.md` is not kept in sync.** It stays as the migration source and the one-shot CLI's default input. No export on save | Your call. Git already holds the file's history |
| R11 | **Merges work on whole entries** (`##` roles, projects, qualifications) and whole sections, not line hunks | Your call, "for now". Matches how CVs are edited and keeps the promote view readable |
| R12 | **Manual "Import `input/CV.md` as master"** action: runs the file through the same merge view (base = the master version it was last imported from) and saves a new master version with `source = import` | Your call. Covers hand edits to the file after migration; cheap given the merge engine |

## Today (what this replaces)

Everything is single-role and file-based:

| Data | Where it lives now |
|---|---|
| Master CV | `input/CV.md` (canonical, in git) |
| Job spec | `input/jobspec.txt` (one at a time; currently the Quantum Base Lead Mobile Engineer spec, uncommitted) |
| CV prompt, research prompt | `input/prompt.md`, `input/research_prompt.md` |
| Steering, steer toggle, theme | Browser localStorage (`cvweb.steering_text`, `cvweb.steering_enabled`, `cvweb.selected_theme`) |
| CV run output | `output/tailored.model-output.txt` (raw), `tailored.model.json` (validated, plus `metadata`), `tailored.md`, PDF/DOCX. Overwritten each run |
| Research inputs | `input/research_company.txt`, `input/research_urls.txt` |
| Research output | `output/research_output.json` / `.md`, formatted PDF. Overwritten each run (currently a "Bridge Probe" test) |
| Older runs | Ad hoc copies: `output/baseline-gemini-2.5-flash/`, `output/step8-opus-fastmode/`, `output/step9-opus/` |

Constraints to keep (AGENTS.md): Python stdlib only, vanilla-JS UI, external tools only via subprocess.

## Concepts (draft)

- **Master CV:** the canonical, complete CV. It's versioned in the DB (R8), which is its record; `input/CV.md` is
  imported once and not kept in sync (R10). It seeds every new role's CV, and any role can merge changes back into it (R1, R7).
- **Role:** one application. It has a name, a company, the job spec text, a status (for example draft, applied,
  closed) and timestamps.
- **Role CV:** every role's own CV, copied from the master when the role is created and then edited independently
  (R1). Runs always use the role's CV. Each role CV remembers the master version it was seeded from or last synced
  with: its **base**. Two sync actions, both three-way merges against that base (R7):
  - **Promote to master** (role → master): the role's changes since the base are shown per entry (R11). The user
    picks which to apply. Removals are unticked by default, so information isn't lost from the master.
  - **Pull from master** (master → role): the master's changes since the base are merged into the role. The role's
    own edits, including removals, survive. Conflicts are shown for the user to resolve.
- **CV run:** one generation for a role. It records the inputs actually sent: provider, model, steering text and
  enabled flag, theme, the prompt version, and a CV snapshot or hash. It also stores the agent output: raw text plus
  validated JSON with `metadata` (warnings, page count). Each role keeps a history of runs; one is "current".
- **Research run:** one research generation for a role. Inputs are the company, URLs and dry-run flag; the output is
  the research JSON/markdown.
- **Rendered output:** the PDF/DOCX made from a run's JSON (`render_tagged_markdown` → `cv_convert`) at view time
  with the chosen theme, cached on disk and treated as disposable.

## Storage options

| Option | Fit | Notes |
|---|---|---|
| **SQLite (stdlib `sqlite3`), JSON in TEXT columns** — recommended | Strong | No new dependency. One file (`cv_web/resumator.db`, gitignored; R9). Relational tables for roles and runs, plus the agent JSON stored whole and queryable with SQLite's JSON functions. "SQL plus documents" in one store, with room to grow |
| JSON/markdown files per role (`roles/<slug>/…`) | OK for now | Git-friendly and readable, but listing, history and querying become hand-written code, and concurrent writes are fragile |
| Document DB (TinyDB, MongoDB…) | Poor | Third-party dependency or server; breaks the stdlib invariant for little gain |
| Postgres | Overkill | Server to run; only worth it for multi-user hosting |

**Leaning:** SQLite for roles, CV versions (master and role), runs and settings; prompts stay files in git. Schema
migrations: a `schema_version` table plus ordered SQL scripts applied on startup.

### CV versions: one table, not a separate master table or `isMaster` flag

Master and role CVs are the same kind of thing (CV source text with history), so one `cv_version` table holds both:

- `role_id NULL` means master. A separate `is_master` flag would only repeat that and could disagree with it; a
  view or helper can expose `is_master` for readability.
- Rows are append-only: an edit, promotion or merge adds a row rather than updating one. The current CV of a role
  (or of the master) is its newest row.
- `parent_id` links each version to the one it came from. `base_master_id` (on role versions) records the master
  version it was last synced with. That's the common ancestor a three-way merge needs (R7).
- `source` records how the version was made: `seed`, `edit`, `promote`, `pull`, `import` or `example`.
- Merging is entry-level (R11). `cv_source.py` already parses the CV into sections and `##` entries, so each side
  becomes a map keyed by section and entry heading. A three-way comparison (base vs role vs master) classifies each
  entry as unchanged, added, removed or changed on one side, or changed on both (a conflict). A change applies as
  the whole entry; a conflict asks the user to pick one side or edit. Prose sections (Profile) and field sections
  (Candidate, Skills, Directives) count as single units. `difflib` is used only to show what changed inside an
  entry. A renamed heading looks like a removal plus an addition; that's acceptable for now.

### Sketch schema (to refine)

```sql
role(id, slug, name, company, status, jobspec TEXT,
     steering_text TEXT, steering_enabled INT, theme TEXT, created_at, updated_at)
cv_version(id, role_id NULL,          -- NULL = master (R8)
           parent_id NULL,            -- previous version of the same CV
           base_master_id NULL,       -- role versions: master version last synced with (merge ancestor)
           source,                    -- seed | edit | promote | pull | import | example
           note NULL, content TEXT, created_at)
cv_run(id, role_id, cv_version_id,    -- the exact CV text the agent saw
       started_at, finished_at, provider, model, theme, steering_text NULL,
       prompt_hash, raw_output TEXT, model_json TEXT, warnings_json TEXT, page_count INT,
       success INT, is_current INT)
research_run(id, role_id, started_at, finished_at, provider, model, company, urls_json, dry_run INT,
             output_json TEXT, output_md TEXT, success INT, is_current INT)
setting(key, value)  -- e.g. last_role_id, first_run_done
```

Run logs stay files under `output/` (they're large and only for debugging); a run row can point at its log path.

## UI (draft)

- **Left sidebar:** a list of roles (name, company, last run date, steered marker). **+** creates a role (name,
  company, paste job spec); its CV starts as a copy of the master (R1). Selecting a role loads its CV, job spec,
  steering, theme, runs and research into the existing tabs.
- **Per-role controls:** steering (moves from localStorage to the role), theme, run history dropdown (pick which
  run's PDF to view), archive and delete role.
- The CV tab edits the role's CV, with **Promote to master** and **Pull from master** actions. Both open a merge view
  (one checkbox per changed entry, conflicts highlighted, with an inline diff) before anything is saved (R7, R11). The master can also be opened
  and edited directly, with its version history. The UI must make clear which CV is open.
- The Research tab is scoped to the selected role.
- The PDF preview renders the selected run on the fly. The 🧭 marker comes from that run's `steering_text`.

## First-run behaviour (R3)

On startup with no database (or an empty one):

1. Create the schema.
2. Ask the user to choose: **example data** (a sample role with a short job spec, a sample master CV and a canned
   run, also useful for demos and tests) or **blank** (an empty master CV template, no roles).
3. Record `first_run_done` so the choice isn't offered again.

## One-time migration of this install (R4)

A CLI command, for example `python3 -m resumator migrate-single-role --name "Quantum Base"`, run once:

- The master CV is imported from `input/CV.md` as master version 1 (`source = import`).
- A role is created from `input/jobspec.txt` (Quantum Base, Lead Mobile Engineer), with its CV seeded from the
  master.
- CV runs: the current `output/tailored.model-output.txt` and `tailored.model.json` (with metadata and steering)
  become its current run. The archived `output/step9-opus/` and `output/step8-opus-fastmode/` are optionally kept
  as history.
- Research: `output/research_output.json` and `.md` are imported into this role, with `input/research_company.txt`
  and `research_urls.txt` as its inputs.
- Steering and theme live in browser localStorage, which the CLI can't read. The UI copies them into the selected
  role on its first load after the migration, if the role has none.
- The command is idempotent: it refuses or skips when the role already exists.

## CLI (R5)

- **One-shot, file-based (unchanged):** `python3 generate_cv.py [--cv …] [--steering-file …] …` and
  `research_role.py` read `input/` and write `output/`, with no DB involved.
- **Role mode:** a single entry point, for example `python3 -m resumator --role "Quantum Base" --action cv` (or
  `research`, `render`, `list`, `create`…). It reads the role's CV, job spec, steering and theme from the DB and
  saves the run back. The existing flags (`--provider`, `--model`, `--theme`, `--no-steering`) override the role's
  settings for that run.
- Open: whether role mode wraps the existing scripts or they gain `--role` directly.

## Steps (draft)

| # | Step | Output | Status |
|---|---|---|---|
| 1 | Decide storage and schema (open questions below); spike SQLite plus JSON functions on the current run files | Decisions recorded | todo |
| 2 | `store.py`: stdlib sqlite3 layer (connect, migrate, role/CV-version/run CRUD) plus tests against a temp DB | Data layer | todo |
| 2a | `cv_merge.py`: entry-level three-way merge on `cv_source` parses (R11), rebuilding the CV text, with tests | Merge engine | todo |
| 3 | Pipeline: `generate_cv` and `research_role` accept a role id (or stay file-based for the CLI) and save each run to the DB; outputs stop overwriting each other | Runs persisted | todo |
| 4 | On-demand rendering: render a stored run's JSON to PDF/DOCX with a theme, with a disposable cache keyed by run id and theme | No stored PDFs | todo |
| 5 | Server API: `/api/roles` (list, create, update, delete, copy master CV), `/api/roles/<id>/runs`, run selection; scope existing endpoints to a role | API | todo |
| 6 | UI: sidebar, **+** dialog, role switching; move steering and theme from localStorage to the role; run-history picker | UI | todo |
| 6a | UI: promote and pull diff/merge view; master editor with version history; "Import `input/CV.md` as master" (R12) | Merge UI | todo |
| 7 | First-run flow (example data or blank) | First run | todo |
| 7a | Role-mode CLI (`--role`, `--action`) beside the unchanged one-shot scripts | CLI | todo |
| 7b | One-time migration command; run it on this install (Quantum Base role, current and archived CV runs, current research) | Migrated | todo |
| 8 | Docs: architecture, cv-format, AGENTS.md, gaps; retire the single-file assumptions | Docs in sync | todo |

## Open questions

- SQLite as recommended, or files-per-role first and SQLite later?
- Backup and export: a JSON dump per role, or just copy `cv_web/resumator.db`?
- Directives (`Emphasise`/`Downplay`) per role: they come with the role's CV copy, so they're already editable per
  role. Confirm that's enough.
- Should prompts be versioned per run (store a hash only, or the full prompt text)?
- Role-mode CLI: wrap the existing scripts, or give them `--role` directly?
- Does the role list need statuses and dates (an application tracker), or just names for now?
- On-demand PDFs: is the Typst render (~1–2 s) fast enough to run on every view, or should it be pre-rendered after
  each run?

## Handoff

For the next session: this is an unrefined TODO captured at the user's request. Start by going through the open
questions with the user (R1–R12 are settled); don't build anything before step 1 is agreed. The related work is in
[cv-format-revamp.md](cv-format-revamp.md) (steering D11/D23, theme picker, run metadata).

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
