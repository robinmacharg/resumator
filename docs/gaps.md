# Gaps and planned work

Priority: **P1** = planned feature, **P2** = correctness or hygiene, **P3** = cleanup.

## P1 — Import an existing CV (upload → master CV)

Today a user has to hand-write the master CV in the format described in [cv-format.md §1](cv-format.md) (the
first-run blank template helps).

Suggested shape:
1. **Upload**: the server only parses JSON bodies. Either add a stdlib multipart parser (`cgi` was removed in Python
   3.13), or have the frontend send `{filename, base64}` as JSON to a new `POST /api/cv/import`. Base64 JSON is the
   simpler option.
2. **Extract text**: `.md`/`.txt` as-is. `.docx`: `pandoc -t gfm`. `.pdf`: `pdftotext -layout` (poppler) if it is on
   PATH; otherwise disable PDF import with a clear reason. All of this goes through subprocess, so no new Python deps.
3. **Normalise with an LLM**: `input/import_prompt.md` (exists) → the selected backend (reuse the attempt loop) → the
   canonical CV.md layout. Instruct the model to preserve every fact, invent nothing, and mark unknown fields as `TODO`.
4. **Review before saving**: show the result in the existing merge dialog (as "Import CV.md" does,
   `role_merge.import_view`), saved as an `import` master version. Nothing is overwritten: older versions stay in
   History.
5. **Validate structurally**: `cv_source.lint_cv_source` (exists) on the imported file.

Touches: `cv_web/server_http_handlers.py` (route), `server_run_helpers.py` (command), a new `import_cv.py` CLI,
a frontend feature module and tab ([static ARCHITECTURE.md checklist](../cv_web/static/ARCHITECTURE.md)), and docs.

## P1 — Steering paragraph for generation

A per-application free-text instruction, for example "emphasise React Native leadership; de-emphasise iOS-only work;
mention the fintech background".

Suggested shape:
1. Done, differently: the web UI has a Steering tab on the CV tab, kept on the role in role mode (in browser
   localStorage while no role is open; copied once into the first role opened), plus a "Steer CV generation" checkbox. Full runs send the text; the server writes it to `output/steering.run.md`
   and passes `--steering-file`, or `--no-steering` when unticked or empty. A 🧭 before the PDF title marks a CV
   generated with steering (from `metadata.steering`).
2. Done: `generate_cv` reads `input/steering.md` (or `--steering-file`) and appends `=== CANDIDATE STEERING ===`
   when it's non-empty ([cv-format.md §2](cv-format.md)).
3. Done: `prompt.md` v2 says steering adjusts emphasis, selection and ordering only and never overrides the
   truthfulness constraints.
4. Optional: pass the steering to `research_role.build_prompt` as well. (Persisting it per job is done: roles.)
5. Done: the steering text is recorded as `metadata.steering` in `tailored.model.json`.

## P2 — Correctness and hygiene

- **`.env` is tracked in git** and holds real API keys. Rotate the keys, `git rm --cached .env`, add a
  `.env.example`, and add `.env` to `.gitignore`. Keys remain in git history until it is rewritten.
- **CV.md content issues**: 54 `[cite: 1]` artefacts left over from a Gemini paste. The `skills_raw` lists are not
  valid YAML (`- "a", "b"`). In the Boostworks role, one bullet is split mid-sentence ("…to give" / "* Customer
  Relations…").
- **No CV.md schema or linter**: in progress. `cv_source.py --lint` checks the v1 source format
  ([cv-source-format.md](cv-source-format.md)); it applies once `input/CV.md` moves to that format
  ([plan](plans/cv-format-revamp.md) step 9).
- **Provider-agnostic messages**: `generate_cv` says "via Gemini CLI" in its argparse help and, on any provider,
  suggests setting `GEMINI_MODEL*` after all attempts fail. It also prints "Gemini CLI returned empty output". The
  log directory is named `gemini_debug_logs` for all providers.
- **Fast mode cuts the end of the CV**: `CV_FAST_MODE` keeps the first 18,000 chars of the prompt text. With the
  v1 source format that drops whole trailing sections (on the v1-format `CV.md`: late projects, Education, Certifications,
  Skills). Truncate per section (for example oldest roles first) or raise the limit.
- **No output history (file mode)**: each file-mode run overwrites `output/tailored*`. Role mode keeps every run
  per role, with its steering ([plan](plans/multi-role.md)).
- **Role research isn't shown**: role research runs are stored (`research_run`), but the Research tab only shows
  the live log; past runs, the formatted output and the research PDF still come from `output/` files. Needs a
  run list in the tab and a research render route (like the CV run PDF).
- **Past run logs aren't shown**: each role run saves its log and raw output, but the UI only shows the live Run
  Log and the picked run's model JSON. A failed run's details need the API (`…/runs/cv/<run>`).
- **Merge limits (promote/pull)**: entry-level only (R11). A renamed heading shows as a removal plus an addition;
  reordering on the incoming side is ignored; section titles show their lower-case key ("in roles"). After a promote
  while master changes are still unpulled, the role's base stays put, so editing a promoted entry again before a
  pull shows as a conflict on the next pull (`cv_web/role_merge.py`). Import has no file-to-master sync the other
  way (R10): master edits never reach `input/CV.md`.
- **Stale venv**: `.venv` is Python 3.9.6, and `generate_cv.py`, `research_role.py` and `cv_convert.py` fail to import
  on it (`int | None` annotations without `from __future__ import annotations`). Things only work because the npm
  scripts fall back to the system `python3`. Rebuild the venv with Python 3.10 or newer.
- **Hard-coded path**: the `stop:server` script in `cv_web/static/package.json` contains an absolute user path.

## P3 — Cleanup

- File mode in the web UI (`[data-file-only]`, the file branches in the feature modules and the `input/`-backed
  editors for CV and job spec) is now only a fallback for an unreachable role API. Remove it, or keep it as an
  explicit "no database" switch.
- Dead code: `run_gemini_with_diagnostics` in both `generate_cv.py` and `research_role.py`. Both have a local
  `load_dotenv_file` that duplicates `env_utils.parse_dotenv_file`.
- `research_role.py` keeps its own `DEFAULT_*_MODEL` and fallback lists that duplicate the backend modules. It should
  rely on `backend.model_sequence`.
- `_split_csv` and `_dedupe` are copied into each backend module. Move them to `backends/base.py` or a shared helper.
- `backend_registry` re-imports and re-interrogates every backend on each call (including the bridge health check).
  Consider a short TTL cache.
- Tests: nothing covers the backends except `claudecode`.
- `gemini-code-*.py` at the root are scratch files.
- DOCX keeps its plain pre-theme look and doesn't mirror the PDF (`themes/docx-styles.xml`). Low priority: PDF is the
  primary output.
