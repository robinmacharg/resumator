# Architecture

## Components

| File | Role |
|---|---|
| `generate_cv.py` | CV pipeline CLI: read inputs → build prompt → backend attempts with model fallback → extract and validate JSON → render tagged markdown → call `cv_convert` |
| `cv_convert.py` | Tagged markdown → PDF (pandoc + typst) and DOCX (pandoc). Also a standalone CLI (the "format only" run) |
| `research_role.py` | Research pipeline CLI: research prompt + company + URLs + CV + job spec → backend → `research_output.md/.json` |
| `research_format.py` | Normalises research markdown → `research_output.formatted.{md,pdf}` |
| `backend_registry.py` | Discovers `backends/*/module.py`, interrogates each, exposes catalog and lookup ([backends.md](backends.md)) |
| `provider_catalog.py` | Frontend-shaped provider catalog. Uses the registry first, falls back to static `model_providers.json` |
| `provider_clients.py` | Transport per provider (`run_<provider>_attempt`) → `AttemptResult`; writes per-attempt logs |
| `env_utils.py` | `.env` parser |
| `cv_web/` | stdlib `http.server` UI wrapper. Runs the CLIs as subprocesses and streams their output |
| `VSCodeExtension/` | VS Code extension that exposes Copilot over local HTTP (`vscodebridge` backend) |

## CV pipeline data flow

```
input/prompt.md ─┐
input/CV.md ─────┼─ build_prompt ─(CV_FAST_MODE: truncate CV to 18k chars + add fast rules)─┐
input/jobspec.txt┘                                                                         │
                       backend.run_attempt(model_i)  ◄── model_sequence (primary + fallbacks)┘
                         │ non-zero rc + transient error (429/503/404/quota) → next model
                         │ other error → exit 1
                         ▼
          output/tailored.model-output.txt (raw) → extract_json_payload → tailored.model.json
                         ▼ parse_and_validate_json_output (strict contract)
                         ▼ render_tagged_markdown
                  output/tailored.md  (YAML front matter + `[tag] line` markup)
                         ▼ cv_convert.convert_markdown_outputs
    tailored.export.md → tailored_dev.pdf      tailored.docx.export.md → tailored_dev.docx
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

## Tests

- `tests/`: unittest coverage for the server helpers, `env_utils` and the `claudecode` backend (with a fake `claude`
  on PATH). Nothing covers `generate_cv`, `cv_convert`, or the other backends.
- `cv_web/static/js/__tests__/`: `node --test` coverage of the frontend feature modules.
