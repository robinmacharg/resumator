# Gaps and planned work

Priority: **P1** = planned feature, **P2** = correctness or hygiene, **P3** = cleanup.

## P1 — Import an existing CV (upload → canonical `input/CV.md`)

Today a user has to hand-write `CV.md` in the format described in [cv-format.md §1](cv-format.md).

Suggested shape:
1. **Upload**: the server only parses JSON bodies. Either add a stdlib multipart parser (`cgi` was removed in Python
   3.13), or have the frontend send `{filename, base64}` as JSON to a new `POST /api/cv/import`. Base64 JSON is the
   simpler option.
2. **Extract text**: `.md`/`.txt` as-is. `.docx`: `pandoc -t gfm`. `.pdf`: `pdftotext -layout` (poppler) if it is on
   PATH; otherwise disable PDF import with a clear reason. All of this goes through subprocess, so no new Python deps.
3. **Normalise with an LLM**: `input/import_prompt.md` (exists) → the selected backend (reuse the attempt loop) → the
   canonical CV.md layout. Instruct the model to preserve every fact, invent nothing, and mark unknown fields as `TODO`.
4. **Review before replacing**: write `output/CV.imported.md` and show a diff or preview. Only an explicit
   "Replace CV" overwrites `input/CV.md` (back up to `input/CV.md.bak`).
5. **Validate structurally**: `cv_source.lint_cv_source` (exists) on the imported file.

Touches: `cv_web/server_http_handlers.py` (route), `server_run_helpers.py` (command), a new `import_cv.py` CLI,
a frontend feature module and tab ([static ARCHITECTURE.md checklist](../cv_web/static/ARCHITECTURE.md)), and docs.

## P1 — Steering paragraph for generation

A per-application free-text instruction, for example "emphasise React Native leadership; de-emphasise iOS-only work;
mention the fintech background".

Suggested shape:
1. New editable file `input/steering.md`: add it to `EDITOR_FILES` in `cv_web/server.py` and `EDITABLE_FILES` in
   `static/app.js`, plus a UI editor (small textarea on the CV tab, or its own tab).
2. In `generate_cv.build_prompt`, append `=== CANDIDATE STEERING ===\n<text>` when the file is non-empty. Append it
   after the job spec and keep append mode, because `{}` placeholders break on the JSON braces in `prompt.md`
   ([cv-format.md §2](cv-format.md)).
3. In `prompt.md`, add a rule that steering adjusts emphasis, selection and ordering only and never overrides the
   truthfulness constraints.
4. Optional: a `--steering-file` CLI flag; pass the steering to `research_role.build_prompt` as well; persist it per
   job alongside the job spec.
5. Record the steering text in the output (for example `metadata.steering` in `tailored.model.json`) so you can see
   which steering produced a given output.

## P2 — Correctness and hygiene

- **`.env` is tracked in git** and holds real API keys. Rotate the keys, `git rm --cached .env`, add a
  `.env.example`, and add `.env` to `.gitignore`. Keys remain in git history until it is rewritten.
- **Prompt input contract doesn't match CV.md**: the uncommitted "Input Contract" block in `prompt.md` describes `—`
  separators and `subsection:` labels. The real file uses YAML front matter plus `#`/`##` headings.
- **CV.md content issues**: 54 `[cite: 1]` artefacts left over from a Gemini paste. The `skills_raw` lists are not
  valid YAML (`- "a", "b"`). In the Boostworks role, one bullet is split mid-sentence ("…to give" / "* Customer
  Relations…").
- **No CV.md schema or linter**: in progress. `cv_source.py --lint` checks the v1 source format
  ([cv-source-format.md](cv-source-format.md)); it applies once `input/CV.md` moves to that format
  ([plan](plans/cv-format-revamp.md) step 9).
- **Provider-agnostic messages**: `generate_cv` says "via Gemini CLI" in its argparse help and, on any provider,
  suggests setting `GEMINI_MODEL*` after all attempts fail. It also prints "Gemini CLI returned empty output". The
  log directory is named `gemini_debug_logs` for all providers.
- **No output history**: each run overwrites `output/tailored*`. Consider `output/<company>-<date>/` snapshots that
  include the job spec and steering.
- **Stale venv**: `.venv` is Python 3.9.6, and `generate_cv.py`, `research_role.py` and `cv_convert.py` fail to import
  on it (`int | None` annotations without `from __future__ import annotations`). Things only work because the npm
  scripts fall back to the system `python3`. Rebuild the venv with Python 3.10 or newer.
- **Hard-coded path**: the `stop:server` script in `cv_web/static/package.json` contains an absolute user path.

## P3 — Cleanup

- Dead code: `run_gemini_with_diagnostics` in both `generate_cv.py` and `research_role.py`. Both have a local
  `load_dotenv_file` that duplicates `env_utils.parse_dotenv_file`.
- `research_role.py` keeps its own `DEFAULT_*_MODEL` and fallback lists that duplicate the backend modules. It should
  rely on `backend.model_sequence`.
- `_split_csv` and `_dedupe` are copied into each backend module. Move them to `backends/base.py` or a shared helper.
- `model_providers.json` defaults have drifted from the module defaults (gemini: `3.5-flash-lite` vs `2.5-flash`).
- `backend_registry` re-imports and re-interrogates every backend on each call (including the bridge health check).
  Consider a short TTL cache.
- Tests: nothing covers `validate_and_normalize_payload`, `render_tagged_markdown`, `cv_convert`, or the backends
  (except `claudecode`).
- `gemini-code-*.py` and `curl.sh` at the root are scratch files.
