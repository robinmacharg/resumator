# Resumator — agent guide

Local tool: master CV (`input/CV.md`) + job spec → LLM → validated JSON → tagged markdown → PDF/DOCX.
Second pipeline: company/role research notes. Python stdlib only; vanilla-JS web UI.

## Read only what the task needs

| Task touches | Read |
|---|---|
| Overall flow, files, web server, run lifecycle | [docs/architecture.md](docs/architecture.md) |
| Adding/changing an LLM provider, env vars, retries | [docs/backends.md](docs/backends.md) |
| CV input format, prompt contract, JSON schema, rendering, PDF, themes (`themes/`) | [docs/cv-format.md](docs/cv-format.md) |
| Master CV source format v1, `cv_source.py` parser/linter, import rules | [docs/cv-source-format.md](docs/cv-source-format.md) |
| Planned work and known issues | [docs/gaps.md](docs/gaps.md) |
| Frontend JS modules, endpoint ownership | [cv_web/static/ARCHITECTURE.md](cv_web/static/ARCHITECTURE.md) |
| VS Code Copilot bridge extension | [VSCodeExtension/README.md](VSCodeExtension/README.md) |

`discussion.txt` is the original brief (superseded by `docs/`). Skip `output/`, `.venv/`, `VSCodeExtension/runtime/`,
`VSCodeExtension/node_modules/`, and `gemini-code-*.py` (scratch).

## Invariants

- No third-party Python deps (`requirements.txt` is empty by design). External tools only via subprocess
  (`gemini`, `pandoc`, `typst`).
- Scripts use cwd-relative `input/` and `output/`: run them from the repo root.
- `input/CV.md` is the user's real CV and `.env` holds real keys. Don't rewrite their content unless asked, and never echo
  `.env` values.
- Model output must pass `validate_and_normalize_payload` in `generate_cv.py`. If you change the JSON contract,
  update `input/prompt.md`, the validator, `render_tagged_markdown`, and `cv_convert.py` together.
- Looks live in `themes/` (Typst theme + Lua filter for PDF, `docx-styles.xml` for DOCX). `cv_convert` emits
  semantic `custom-style` markup only, never raw Typst or hard-coded sizes.
- The backend plugin contract lives in `backends/base.py`. New providers go in `backends/<id>/module.py`, with no
  registry edits (see docs/backends.md).

## Commands (repo root)

```bash
python3 -m cv_web                                   # UI at http://127.0.0.1:8765
python3 generate_cv.py [--provider ID] [--model M] [--cv PATH] [--theme T] [--steering-file F | --no-steering]  # CV pipeline (steering default: input/steering.md)
python3 cv_convert.py [--theme compact]             # re-render output/tailored.md only (looks: themes/)
python3 research_role.py --company-name "X" [--url U ...] [--dry-run]
python3 research_format.py
python3 cv_source.py --lint [path]                  # lint a CV source file (default input/CV.md)
python3 -m unittest discover -s tests -v            # Python tests (server helpers, env_utils, cv_source, contract, backends)
(cd cv_web/static && npm test)                      # frontend tests (node --test)
```

## Doc upkeep

When a change alters something these docs describe, update the matching doc in the same change. Keep them terse:
tables and bullets, and name functions rather than line numbers.
