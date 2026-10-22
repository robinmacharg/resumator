# Resumator — agent guide

Local tool: master CV + job spec → LLM → validated JSON → tagged markdown → PDF/DOCX, per job application ("role").
Roles, versioned CVs and runs live in SQLite (`cv_web/resumator.db`); the one-shot scripts still work on `input/`
and `output/` files. Second pipeline: company/role research notes. Python stdlib only; vanilla-JS web UI.

## Read only what the task needs

| Task touches | Read |
|---|---|
| Overall flow, files, web server, run lifecycle | [docs/architecture.md](docs/architecture.md) |
| Adding/changing an LLM provider, env vars, retries | [docs/backends.md](docs/backends.md) |
| CV input format, prompt contract, JSON schema, rendering, PDF, themes (`themes/`) | [docs/cv-format.md](docs/cv-format.md) |
| Master CV source format v1, `cv_source.py` parser/linter, import rules | [docs/cv-source-format.md](docs/cv-source-format.md) |
| Planned work and known issues | [docs/gaps.md](docs/gaps.md) |
| Writing or continuing a plan (layout, end-of-task and new-session rules) | [docs/plans/README.md](docs/plans/README.md) |
| Settings in the DB (`.env` removal; decisions D1–D11) | [docs/plans/settings-in-db/index.md](docs/plans/settings-in-db/index.md) |
| DB schema and ER diagram (keep current with `store.MIGRATIONS`) | [docs/db-schema.md](docs/db-schema.md) |
| Roles, merge, first run, role CLI (decisions R1–R21) | [docs/plans/multi-role-design.md](docs/plans/multi-role-design.md) |
| Frontend JS modules, endpoint ownership | [cv_web/static/ARCHITECTURE.md](cv_web/static/ARCHITECTURE.md) |
| VS Code Copilot bridge extension | [VSCodeExtension/README.md](VSCodeExtension/README.md) |

`examples/` holds fictional first-run data (master CV, job spec, canned run, blank template); keep it fictional.
`discussion.txt` is the original brief (superseded by `docs/`). Skip `output/`, `.venv/`, `VSCodeExtension/runtime/`,
`VSCodeExtension/node_modules/`, and `gemini-code-*.py` (scratch).

## Invariants

- Python 3.11+ (tests use `unittest` `enterContext`). No third-party Python deps (`requirements.txt` is empty by
  design). External tools only via subprocess (`gemini`, `pandoc`, `typst`).
- Scripts use cwd-relative `input/` and `output/`: run them from the repo root.
- `input/CV.md` is the user's real CV and `.env` holds real keys. Don't rewrite their content unless asked, and never echo
  `.env` values. `cv_web/resumator.db` holds the user's real roles and CVs: don't write to it in checks. Copy it
  with SQLite's backup API and use `--db` (CLI) or `server_roles.DB_PATH` (server) on the copy.
- Schema changes are a new `store.MIGRATIONS` entry; never edit an applied migration. Update the ER diagram in
  [docs/db-schema.md](docs/db-schema.md) in the same change.
- Model output must pass `validate_and_normalize_payload` in `generate_cv.py`. If you change the JSON contract,
  update `input/prompt.md`, the validator, `render_tagged_markdown`, and `cv_convert.py` together.
- Looks live in `themes/` (Typst theme + Lua filter for PDF, `docx-styles.xml` for DOCX). `cv_convert` emits
  semantic `custom-style` markup only, never raw Typst or hard-coded sizes.
- The backend plugin contract lives in `backends/base.py`. New providers go in `backends/<id>/module.py`, with no
  registry edits (see docs/backends.md).

## Commands (repo root)

```bash
python3 -m cv_web                                   # UI at http://127.0.0.1:8765
python3 generate_cv.py [--provider ID] [--model M] [--cv PATH] [--theme T] [--fast] [--font-priority F] [--db F] [--steering-file F | --no-steering]  # CV pipeline (steering default: input/steering.md; settings from the DB)
python3 cv_convert.py [--theme compact]             # re-render output/tailored.md only (looks: themes/)
python3 research_role.py --company-name "X" [--url U ...] [--dry-run]
python3 generate_cv.py --io json < request.json     # also research_role.py: JSON request in, JSON result out, no files
python3 research_format.py
python3 -m resumator --action list|create|cv|research|render|backup|setup|settings-import|settings-export|settings-set|settings-test|migrate-single-role [--role R] [--db F]  # role-mode CLI (DB)
python3 -m cv_web.migrate_single_role --name "Role" [--archive DIR]  # one-time: this install's files → first role in the DB
python3 cv_source.py --lint [path]                  # lint a CV source file (default input/CV.md)
python3 -m unittest discover -s tests -v            # Python tests (server helpers, env_utils, cv_source, cv_merge, store, role_merge, role_runner, server_roles, migrate_single_role, first_run, resumator CLI, contract, backends, --io json)
(cd cv_web/static && npm test)                      # frontend tests (node --test)
```

## Plans and sessions

Plans follow [docs/plans/README.md](docs/plans/README.md): a folder per plan with an index, design, one file per
task and a log. At the end of a task or session, say whether to start a new session (with a handover prompt) or stay,
and why.

## Doc upkeep

When a change alters something these docs describe, update the matching doc in the same change. Keep them terse:
tables and bullets, and name functions rather than line numbers.
