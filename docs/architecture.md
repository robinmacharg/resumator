# Architecture

## Components

| File | Role |
|---|---|
| `generate_cv.py` | CV pipeline CLI: read inputs → build prompt → backend attempts with model fallback → extract and validate JSON → render tagged markdown → call `cv_convert` |
| `cv_source.py` | Master CV source format: parse → dict, comment-stripped prompt text, elided phrases, linter CLI ([cv-source-format.md](cv-source-format.md)). Not yet wired into the pipeline |
| `cv_convert.py` | Tagged markdown → semantic markdown → PDF (pandoc + typst) and DOCX (pandoc). Looks come from `themes/` ([cv-format.md §5](cv-format.md#5-conversion-cv_convertpy)). Also a standalone CLI (the "format only" run). `render_cv` does the same in memory (bytes out, no files) for role runs; `count_pdf_pages` reads PDF bytes |
| `research_role.py` | Research pipeline CLI: research prompt + company + URLs + CV + job spec → backend → `research_output.md/.json` |
| `pipe_io.py` | `--io json` harness for both pipelines (`run_json_io`): one JSON request on stdin, progress on stderr, one JSON result on stdout, no data files. fd 1 points at stderr while the run works, so stray prints can't corrupt the result. Not yet used by the server ([plan](plans/multi-role.md), "Run I/O") |
| `research_format.py` | Normalises research markdown → `research_output.formatted.{md,pdf}` |
| `backend_registry.py` | Discovers `backends/*/module.py`, interrogates each, exposes catalog and lookup ([backends.md](backends.md)) |
| `provider_catalog.py` | Frontend-shaped provider catalog. Uses the registry first, falls back to static `model_providers.json` |
| `provider_clients.py` | Transport per provider (`run_<provider>_attempt`) → `AttemptResult`; writes per-attempt logs |
| `env_utils.py` | `.env` parser |
| `cv_web/` | stdlib `http.server` UI wrapper. Runs the CLIs as subprocesses and streams their output |
| `cv_merge.py` | Entry-level three-way merge of CV source text (`split_units`, `compare`, `merge`) for promote/pull between master and role CVs. Pure functions, used by `cv_web/role_merge.py` |
| `cv_web/store.py` | SQLite data layer for the multi-role workspace (`cv_web/resumator.db`, gitignored): migrations, roles, master/role CV versions, prompt versions, CV and research runs, settings, `backup`. Used by `server_roles`, `role_runner` and `migrate_single_role` ([plan](plans/multi-role.md)) |
| `cv_web/role_runner.py` | Role runs (`run_cv`, `run_research`): builds the `--io json` request from the store (role CV, job spec, steering, theme, prompt template text saved as a `prompt_version`), runs the script from the repo root, streams stderr to an `on_log` callback, and saves the `cv_run`/`research_run` row with the log (errors appended). Returns `pdf_base64` without storing it. Called by `server_roles` (the role CLI follows in [plan](plans/multi-role.md) step 13) |
| `cv_web/role_merge.py` | Promote and pull (`view`, `parse_decisions`, `apply`): three-way merge of the role CV and the master against the role's `base_master_id` version, saved as a `promote` master version or a `pull` role version. A pull moves the role's base to the current master; a promote moves it (with an unchanged-content `promote` role version) only when nothing is left to pull. Also "Import `input/CV.md` as master" (`import_view`, `apply_import`, R12): base = the file text at the last import (setting `master_import_text`, else the newest `import` version), saved as an `import` master version. Called by `server_roles` |
| `cv_web/server_roles.py` | Role API (`dispatch`, tried by `server_http_handlers` for every GET/POST): roles, role and master CVs, run history, role runs in the background (sharing the run locks and live state), and run PDF/DOCX rendered from `raw_output` through the in-memory `RENDER_CACHE`. See "Role API" below |
| `cv_web/migrate_single_role.py` | One-time CLI (`python3 -m cv_web.migrate_single_role --name … [--archive DIR] [--no-research]`): imports `input/CV.md` as a master `import` version and a first role (job spec, seeded CV, current and archived CV runs, research run) from today's `input/`/`output/` files. Provider, model, theme and prompt hash stay NULL (not recorded in those files). Skips when the role exists; one transaction |
| `VSCodeExtension/` | VS Code extension that exposes Copilot over local HTTP (`vscodebridge` backend) |

## CV pipeline data flow

```
input/prompt.md ─┐
input/CV.md ─────┼─ cv_source parse + lint ─ build_prompt (+ RUN FACTS, + steering.md)
input/jobspec.txt┘   ─(CV_FAST_MODE: truncate CV to 18k chars + add fast rules)───────────────┐
                                                                                            │
                       backend.run_attempt(model_i)  ◄── model_sequence (primary + fallbacks)┘
                         │ non-zero rc + transient error (429/503/404/quota) → next model
                         │ other error → exit 1
                         ▼
          output/tailored.model-output.txt (raw) → extract_json_payload → tailored.model.json
                         ▼ parse_and_validate_json_output (strict contract; rule breaches → warnings)
                         ▼ render_tagged_markdown (directives) → find_elision_leaks
                  output/tailored.md  (YAML front matter + `[tag] line` markup)
                         ▼ cv_convert.convert_markdown_outputs
    tailored.export.md (custom-style divs) ─┬─ styles.lua + themes/*.typ ──► tailored_dev.pdf
                                            └─ reference.docx (+ docx-styles.xml) ──► tailored_dev.docx
                         ▼ count_pdf_file_pages → record_run_metadata (warnings, page count, steering → tailored.model.json)
```

Format details: [cv-format.md](cv-format.md).

## Research pipeline

`research_prompt.md` (`{company_name} {urls_block} {jobspec_content} {cv_content}` placeholders, or appended
sections if none are present) → backend (same fallback loop, with extra Gemini 429 handling) →
`output/research_output.{md,json}` and `research_prompt.built.txt`. The company name and URLs persist to
`input/research_company.txt` and `input/research_urls.txt`. "Reset prompt" copies `research_prompt.default.md` over
`research_prompt.md`. `--dry-run` only builds the prompt.

## File contract

- `input/` holds the user-editable sources (tracked in git).
- `output/` holds generated files (gitignored). Every run overwrites them; there is no per-application history.
- `output/gemini_debug_logs/` holds one log per attempt for all providers, despite the name. File names are
  `{cv-attempt|research-attempt}-NN-<model>-<ts>.log`.
- `--io json` (both pipelines) touches none of this: inputs come in the request, attempt logs go to stderr, and the
  CV result carries the PDF as `pdf_base64` (`cv_convert.render_cv`). Shapes: `run_cv` / `new_cv_result` in
  `generate_cv.py`, `handle_json_request` in `research_role.py`.
- `.env` sits at the repo root. Its values override OS env (`backend_registry.runtime_env`).

## Web wrapper (`cv_web/`)

- Entry: `python3 -m cv_web` → `server.py` (composition root), 127.0.0.1:8765.
- Editable files (`EDITOR_FILES` in `server.py`, mirrored by `EDITABLE_FILES` in `static/app.js`): `cv`, `prompt`,
  `research_prompt`, `jobspec`, `env`.
- `/output/<name>` only serves `ALLOWED_OUTPUT_FILES`.
- Runs: `server_run_helpers.make_command` builds `generate_cv.py` (full) or `cv_convert.py --pdf --docx` (format)
  commands. `server_process_runners` streams stdout and stderr into runtime state, and the UI polls
  `/api/run/status`. There is one run lock for CV and one for research. Research can be stopped.
- Provider and model dropdowns come from `provider_catalog.load_provider_catalog` via `/api/state`.
- Request bodies are JSON only. There is no multipart/file-upload handling yet ([gaps.md](gaps.md)).
- Module map and endpoint ownership: [cv_web/static/ARCHITECTURE.md](../cv_web/static/ARCHITECTURE.md).

### Role API (`server_roles.py`)

JSON in and out, camelCase keys (store rows converted by `camel`). Errors are `{error}` with 400 (bad request), 404
(unknown role or a run of another role), 409 (conflict: run in progress, no master, nothing to render) or 500.
The UI uses them whenever the DB has roles ("role mode", `role-workspace-feature.js` and `role-runs-feature.js`;
see [static/ARCHITECTURE.md](../cv_web/static/ARCHITECTURE.md)). With no roles it keeps the file-based endpoints above,
which are unchanged. In role mode the CV and job spec editors never reach them, so `input/CV.md` isn't overwritten;
the prompt and `.env` editors stay file-based. Role research runs are stored, but the UI doesn't list or render
them yet (see [gaps.md](gaps.md)).

| Route | What |
|---|---|
| `GET /api/roles[?status=]` | Role list (R20): role fields plus `lastRunAt`, `currentSteered` |
| `POST /api/roles` | Create `{name, company, jobspec, status, theme, steeringText, steeringEnabled, slug}`; seeds its CV from the master (409 without one) |
| `GET`/`POST /api/roles/<id>` | Read / update the same fields. Archive = `{status: "closed"}` (R21); `theme: ""` = default |
| `POST /api/roles/<id>/delete` | Delete the role, its CV versions and runs (409 while its run is live) |
| `GET`/`POST /api/roles/<id>/cv`, `/api/master/cv` | Current CV and version list (no content) / save `{content, note}` as an `edit` version (`unchanged: true` when identical) |
| `GET /api/roles/<id>/merge?direction=promote\|pull` | Merge view: `{direction, baseId, targetId, sourceId, baseBehind, changes}`. Each change has `key` (`[section, entry]`), `kind`, `heading`, `status` (`added`/`removed`/`changed`/`conflict`), `base`/`current`/`incoming` text, `diff` and the default `accept` (removals and conflicts unticked). Promote: target = master, source = role; pull: the reverse |
| `POST /api/roles/<id>/merge` | Save `{direction, targetId, sourceId, accept: [key…], resolutions: [{key, choice: current\|incoming\|edit, text}], note}`; blank edited text drops the entry. Every conflict needs a resolution (400); 409 when either CV changed since the view. Returns `{unchanged, versionId, baseMoved, roleCv, masterCv}` |
| `GET /api/roles/<id>/cv/versions/<v>`, `/api/master/cv/versions/<v>` | One version of that CV with its content (404 for another CV's version) |
| `POST …/cv/versions/<v>/restore` (role or master) | Restore it as a new `edit` version, note "Restored version N" (`unchanged: true` when identical). Same response as a CV save |
| `GET /api/master/import` | Import merge view for `input/CV.md`: `{direction: "import", baseFrom (lastImport\|importVersion\|none), targetId, sourceHash, changes}`, changes as for `…/merge` (409 when the file can't be read) |
| `POST /api/master/import` | Save `{targetId, sourceHash, accept, resolutions, note}` as an `import` master version; the file text becomes the next base even when nothing was accepted. 409 when the master or the file changed since the view. Returns `{unchanged, versionId, masterCv}` |
| `GET /api/roles/<id>/runs` | `{cvRuns, researchRuns}`, newest first, without large text |
| `GET /api/roles/<id>/runs/<cv\|research>/<run>` | One run in full (raw output, model JSON, log) |
| `POST /api/roles/<id>/runs/<cv\|research>/<run>/current` | Make a successful run current |
| `POST /api/roles/<id>/runs/cv` | Start `{selectedProvider, selectedModel, theme, steering}` (null/absent = the role's). Progress on `/api/run/status` (`kind: role-cv`, `roleId`, then `runId`, `error`) |
| `POST /api/roles/<id>/runs/research` | Start `{selectedProvider, selectedModel, company, urls, dryRun}`. Progress on `/api/research/status`; `/api/research/stop` stops it |
| `GET /api/roles/<id>/runs/cv/<run>/cv.<pdf\|docx>[?theme=]` | Rendered from the run's `raw_output` (validated as on its run day, with its CV version's directives). No `theme` = the run's; `theme=` = default. Cached in memory by (run, theme, format), 32 entries, lost on restart; a finished run warms its own PDF (R16) |

## Tests

- `tests/`: unittest coverage for the server helpers, `env_utils`, `cv_source`, `cv_merge`, `store` (temp DBs), `role_merge` (temp DB), `role_runner` (real scripts on a temp DB with a fake `claude`), `server_roles` (temp DB; rendering and runs patched), `migrate_single_role` (fixture files), `cv_convert` (render tests skip
  without pandoc/typst; the in-memory vs file-route parity test also skips without a local `output/tailored.md`) and the `claudecode` backend (with a fake `claude` on PATH). Nothing covers `generate_cv` or
  the other backends.
- `cv_web/static/js/__tests__/`: `node --test` coverage of the frontend feature modules.
