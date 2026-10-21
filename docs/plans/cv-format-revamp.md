# Plan: CV format revamp

**Goal:** one human-editable, agent-friendly master CV format; rules for an agent to import any existing CV into it;
a revised generation contract whose output matches the target layout; and styling that lives in theme files rather
than in code.

**Status:** steps 1–8 done; step 9 run, comparison and page-fit changes done; 13 lines still over 2 pages (Open questions). See [Handoff](#handoff).

## Why

- `input/CV.md` is a de facto format that only the LLM reads. It uses YAML front matter (invalid in places, and there
  is no stdlib YAML parser), `[cite: 1]` residue, and a prompt "Input Contract" that describes a different layout
  ([gaps.md](../gaps.md)).
- Source CVs arrive in inconsistent shapes, so the output varies.
- The output requirements (below) differ in several places from the current JSON contract and renderer.
- Styling is hard-coded in Python string templates in `cv_convert.py`, so small style tweaks mean code changes.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Source format is markdown with `# section` / `## entry` / `Key: value` / `- bullet`. No YAML | Easy to edit; parses with the stdlib (project invariant: no third-party deps) |
| D2 | The source is neutral and exhaustive: one `# Roles` list, with no "recent" vs "earlier" split | Selection is per job, so it's the generator's job, not the author's |
| D3 | `~~elided~~` text **is sent to the model** as context but must never be printed. The code checks the output for elided phrases afterwards. `<!-- -->` comments are stripped before prompting | Your call: hidden text adds useful context. Easy to reverse later |
| D4 | `"Quotes"` are plain text: no escaping, no special meaning. The model may reword or drop quoted phrases | The aim was friction-free typing, not a verbatim rule |
| D5 | Keep the JSON intermediate and its validator; revise the schema (v2) instead of having the model emit Typst or markdown | Validation catches broken output early; the renderer owns the layout |
| D6 | **Styling lives in theme files, not code.** The renderer emits semantic markup only (every element gets a named style such as `role-heading`, `keywords`, `earlier-role`). A Typst theme file and a DOCX reference document map those names to looks. Style presets (including smaller font sizes for page fit) are alternative theme files | "Make this field italic" becomes a one-line theme edit. Presets give the UI something to offer later |
| D7 | Dates are `Mon YYYY` (three-letter month) or `YYYY` in both the source and the output | Your call |
| D8 | Contact links line is on by default and switchable with a directive (`Contact links: no`). Extra subheader lines come from repeatable `Subheader:` fields | Your call. UI checkbox deferred |
| D9 | Earlier career line keeps the current format: `**Title** \| _Company_ (skills) - Mon YYYY - Mon YYYY` | Your call, matching the existing generated CV |
| D10 | Add the Claude Code backend **next**, before the contract and pipeline work | See "Backend order" below |
| D11 | **Steering:** optional `input/steering.md` holding the user's free text. When it's non-empty, `build_prompt` appends a `=== CANDIDATE STEERING ===` section that wraps the text in agent instructions (below). Empty or missing means no section. No UI changes for now: edit the file directly | Your call. The file stands in for a UI field |
| D12 | The Copilot comparison run comes last (step 11), once the pipeline is stable | Saves Copilot tokens |
| D13 | **PDF is the primary format; DOCX is second-class.** DOCX styling is a text file, `themes/docx-styles.xml`, merged into pandoc's default reference doc at render time (no binary in git). In step 6 DOCX keeps today's plain pandoc look; matching it to the PDF comes later, if ever | Your call. Word niceties can wait |
| D14 | Step 6's "looks the same" allows the tidier spacing from the spike ("(AppStore)", single spaces around `\|` in the links line) | Your call. Today's stray spaces were artefacts |
| D15 | Contract v2 drops `semantic_tags` and `skills_raw`. The model supplies values only; code builds every heading, label and fixed phrase ("Targeted Requirements Match for …", "Title \| Company", the earlier-career date span) | Step 7 call, open to review. The tags were an echo the renderer already owns, `skills_raw` echoed the input, and fixed text can't drift if the model never writes it |
| D16 | Directives are applied in the renderer as well as told to the model: `contact_links` drops the links line, `Omit: keywords` drops keyword lines | Step 7 call. The output obeys the directive even when the model doesn't |
| D17 | **Misbehaving runs warn, they don't fail, when the output still renders.** A selected role that starts before the cutoff is a warning (a year-only start counts as December). Hard failures are kept for output that can't render. Every warning must reach the user (CLI now; recorded in the output for the later UI) | Your call (revised from the step 7 draft, which failed the run). Faulty output the user may not spot is worse than a noisy run |
| D18 | The Earlier Career Highlights intro span is years only: `YYYY - YYYY` (or `- Present`) | Your call |
| D19 | `generate_cv` stops before the model call when `lint_cv_source` reports errors. A single-point `date_range` (`2016`) is valid output | Step 8 calls, open to review. A broken source wastes a model call. The source allows `Dates: 2016`, and Opus copied it faithfully |
| D20 | Earlier career is capped at 8 items (merge related older roles before dropping any; drop the oldest and least relevant first) and technical skills at 4–5 groups. Going over warns (D17) | Your call (step 9). 15 earlier lines and 8 skill groups pushed the CV to 3 pages |
| D21 | **Standing weightings are data, not prompt text.** Repeatable `Emphasise:` / `Downplay:` directives in the CV's `# Directives` (currently AI-assisted development, AI tooling, LLM applications / Android), passed in RUN FACTS. `prompt.md` has one generic "Weightings" rule. Precedence: truthfulness, then the job spec's requirements, then steering (per job), then weightings (standing) | Your call to weight them; the mechanism was my call. Swapping topics is a one-line CV edit with no prompt change |
| D22 | Sector lists in the earlier-career intro use a serial comma | Your call. Sectors that contain "and" ran together |
| D23 | Steering UI: a Steering tab (localStorage only) and a "Steer CV generation" checkbox, both persisted. Full runs send `{enabled, text}`; the server passes `--steering-file output/steering.run.md` or `--no-steering`. The 🧭 before the PDF title comes from the shown CV's `metadata.steering`, so it reflects how that PDF was made, not the current checkbox | Your request; indicator source was my call. Ticking or unticking doesn't change an existing PDF |

### Backend order (D10)

Add `backends/claudecode/` before steps 5–9, for these reasons:

- It's small and isolated. The plugin contract needs only `backends/claudecode/module.py` and no registry edits, and
  `backends/gemini` is already a subprocess-CLI template. `claude -p --output-format json --model … --json-schema …`
  fits the "external tools only via subprocess" invariant.
- Steps 5–9 are where most LLM calls happen (import-prompt tuning, contract v2 iterations, end-to-end runs). Doing
  them on the larger allowance saves Copilot tokens for comparison runs.
- A baseline run of the *current* pipeline on both backends shows the quality gap before anything changes, so
  later differences can be attributed to the contract rather than the model.
- Testing contract v2 against two models stops the prompt from being tuned to one model's quirks.

Watch for: `claude -p` brings its own system prompt, tools and project context. The backend should run it with tools
disabled from a neutral working directory (check the exact flags when implementing). `--json-schema` may let the CLI
enforce the contract directly; the existing validator stays as the backstop.

### Steering section (D11)

Draft of what `build_prompt` appends when `input/steering.md` is non-empty (finalise in step 7):

```text
=== CANDIDATE STEERING ===
In addition to the job specification, the candidate wants this CV to emphasise the following. Use it to guide
which roles, bullets, skills and projects you select, how you order them, and how you phrase the headline and
summary. It never overrides the truthfulness rules: do not invent or stretch facts to satisfy it. If it conflicts
with the job specification, favour the job specification and lean towards the steering where the evidence allows.

Steering: "multi-domain skills"
```

The quoted text is the file's content, trimmed. Append mode, as now, because `prompt.md` contains literal JSON
braces ([cv-format.md §2](../cv-format.md)).

## Output requirements (target layout)

Recorded from the brief so later steps can check against it.

1. Candidate name at the top.
2. Subheader: a headline blending the candidate's primary relevance for the role with their actual career titles;
   contact info (phone, email); the contact links line (D8); any extra `Subheader:` lines.
3. Professional summary: one-liners, each opening with a bold phrase that leads into a 1–2 line sentence. Then a
   "Targeted Requirements Match for \<ROLE TITLE\>" subsection listing role-specific skills.
4. Education, Certifications & Credentials: 1–3 relevant points; discount irrelevant ones.
5. Selected Key Roles: only the most relevant roles started in the last 10 years, at most 5. Each has
   **Title | Company**, then `Mon YYYY - Mon YYYY|Present (App Store link if any)`, then `Keywords: …`, then 4–5
   bullets of relevant experience reworded for the role.
6. Earlier Career Highlights: subtitle "\<earliest\> - \<latest\> Positions across \<relevant sectors\>", then one
   line per role in the D9 format.
7. Open Source Contributions: the 3–4 most relevant.
8. Technical Skills and Expertise: role-specific, grouped by area (languages, devops, mobile, frontend,
   management…).
9. Aim for two PDF pages. The pipeline reports the page count; fitting (smaller-font theme preset, or asking the model
   to compact) is a later UI feature.

### Gap analysis: requirements vs current contract (input to step 7)

| Req. | Current | Change needed |
|---|---|---|
| 2 headline | `candidate.title` copied from the CV | New generated `document.headline` |
| 2 contact | phone/email plus social links line | Keep; add `Contact links` directive and `Subheader:` lines (D8) |
| 3 summary | 4–5 items | Keep; add a length guide (≤ ~200 chars) |
| 3 requirements | heading is "dynamic" free text | Fixed `Targeted Requirements Match for {role_title}`; model supplies `role_title` only |
| 4 education | ≥2 | 1–3 |
| 5 roles | `bullet_primary` + `bullet_secondary` | One `bullets` list, 4–5. App Store link from source `Link: App Store …`. Keywords line left out when `Omit: keywords` is set |
| 5 window | prompt rule only | Compute the 10-year cutoff in code and pass it in the prompt; validate start dates against it |
| 5/6 dates | `normalize_month_year_range` outputs full month names ("October 2021") | Three-letter months (D7) |
| 6 earlier | `**Role** \| _Company_ (tech) - dates` | Line format unchanged (D9); intro built from structured `sectors` plus computed date span |
| 7 open source | 3–5 | 3–4 |
| 9 two pages | not checked | Report the PDF page count after render (exposed for the later UI) |
| D3 elision | n/a | Post-generation check: warn if any elided phrase appears in the output |
| D6 styling | Typst snippets hard-coded in `cv_convert.apply_semantic_tag_formatting` | Semantic markup plus theme files (step 6) |

## Steps

| # | Step | Output | Status |
|---|---|---|---|
| 1 | Draft the source format and import rules | [docs/cv-source-format.md](../cv-source-format.md) | done |
| 2 | Convert the attached 2023 PDF CV to the draft format | [input/CV.v2.md](../../input/CV.v2.md) (`input/CV.md` untouched) | done |
| 3 | Review gate: format and conversion reviewed, questions answered | D3, D4, D7–D10 | done |
| 4 | Claude Code backend: `backends/claudecode/module.py` (`claude -p`, JSON output, model selection, tools off) plus a smoke test. Baseline: run the current pipeline on Claude and compare with the existing `tailored_dev.pdf` | Second backend, baseline comparison | done |
| 5 | Formalise the source format: `cv_source.py` (stdlib parse → dict, strip comments, collect elided phrases, apply directives, lint required fields, date forms, `TODO`s and unknown keys) plus tests; finalise the spec; `input/import_prompt.md` from the import rules | Parser, linter, spec | done |
| 6 | Styling: spike how pandoc carries named styles (fenced divs/spans with `custom-style`: DOCX supports them natively; Typst probably needs a small pandoc Lua filter mapping them to theme functions). Then move all current looks into `themes/default.typ` + `themes/docx-styles.xml` (D13), and add one compact preset | Theme files; `cv_convert` emits no styling | done |
| 7 | `prompt.md` v2. **Input contract:** replace the stale "Input Contract" block (it describes `—` separators and `subsection:` labels) with a short description of the new source format: sections, entries, fields, elision means context-only (D3), comments already stripped, directives, `TODO`. **Output contract:** rewrite per the gap table. Also add the steering rule (D11). Then update `validate_and_normalize_payload` and `render_tagged_markdown` (semantic names from step 6); add tests for the validator and renderer | Revised contract | done |
| 8 | Wire the pipeline: `generate_cv` parses the source, sends it (comments stripped) plus computed facts (today, 10-year cutoff, directives) to the model; elision check and page count after render (read the PDF's `/Pages /Count`; counting `/Type /Page` markers over-counts). Steering (D11): read `input/steering.md` if present, append the section, record the text as `metadata.steering` in `tailored.model.json`. No UI or `EDITOR_FILES` changes | End-to-end run | done |
| 9 | Swap in: replace `input/CV.md` with the reviewed v2 (back up the old one); run the full pipeline on Claude against the current job spec; compare with the step 4 baselines | Real output | todo |
| 10 | Docs: update `cv-format.md`, `backends.md`, `gaps.md` (P2 schema/linter items resolved; P1 import narrowed), `AGENTS.md` | Docs in sync | todo |
| 11 | Copilot comparison (D12): one run via the VS Code bridge on the final pipeline; three-way comparison with Claude and the Gemini baseline | Comparison notes | todo |
| — | Later (UI): steering field (D11); CV import (upload → extract → `import_prompt.md` → lint → review/replace); page-fit controls (theme preset or "compact" request); directive checkboxes | | later |

## Handoff

For the next session. Read this section, the Decisions table and the step you're on; skip the Log unless needed.

- **Branch:** `improvement/20261021-integrate-claude-revamp-cv-format` (off `develop`). Steps 1–7 committed; step 8
  is uncommitted.
- **Working agreement:** stop and report after each step; update the docs in the same step
  ([AGENTS.md](../../AGENTS.md) "Doc upkeep"); add a Log line; commit only when asked. No UI changes unless asked.
- **Step 8 result:** `generate_cv.main` parses and lints the CV (`--cv PATH`, default `input/CV.md`), appends RUN
  FACTS and steering, passes `role_cutoff` and `directives`, and collects warnings (rule breaches, elision leaks,
  pages > 2). They print and go into `metadata` of `tailored.model.json` with `page_count` and `steering`. Details in
  [cv-format.md §2–3](../cv-format.md).
- **State:** swap done: `input/CV.md` is the v2 source and the old file is `input/CV.v1.md` (both via `git mv`). The
  web UI server was restarted and lists Claude Code as enabled and the default (first enabled backend). It needs no
  key: the `claude` CLI's own login is used.
- **Step 9 result:** with fast mode off, Opus is still **3 pages** (about 24 lines onto page 3; 9 with
  `--theme compact`). The degree is back in Education, which confirms the step 8 gap was fast-mode truncation. The
  overflow comes from the contract, not the model: rule 12 asks for every other role (15 earlier-career lines), and
  rule 17 sets no cap on skill groups (8). Outputs: `output/tailored*` (this run) and `output/step8-opus-fastmode/`.
- **Step 9 page fit (D20–D22):** with the caps and weightings, Opus kept to 8 earlier items and 5 skill groups, but
  is still **3 pages** (13 lines over; it was 24). The compact theme fits it on 2 pages. Android mentions went from 6
  to 0, and AI now has a summary entry, a requirement match and a skill group. Outputs: `output/tailored*` (latest),
  `output/step9-opus/` (before the caps), `output/step8-opus-fastmode/`.
- **Next:** the remaining page-fit and Android questions (Open questions), then step 10.
  - `input/jobspec.txt` has an uncommitted user edit (Quantum Base, Lead Mobile Engineer). The user accepted that
    run as the step 9 result; no like-for-like Kodly rerun.
  - `CV.md` has no `~~elided~~` text, so the elision check has only unit-test coverage. Steering has not been
    tried live either.
- **Gotchas:**
  - Run scripts from the repo root (cwd-relative `input/` and `output/`).
  - Never echo `.env` values.
  - In zsh, `echo ====X` fails (`=cmd` expansion), so quote it.
  - `pdftoppm` isn't installed, so PDFs can't be viewed as images. `mdls -name kMDItemNumberOfPages` can be stale
    after a re-render: run `mdimport <pdf>` first (it gave 2 for a 3-page PDF). The pipeline's own page count is
    reliable.
  - `output/` is gitignored; the baselines live in `output/baseline-gemini-2.5-flash/` and the latest Opus run is in
    `output/tailored*`.

## Open questions

- **Remaining page fit.** After D20 the output is still 13 lines over on the default theme (2 pages with compact).
  The bulk is 25 role bullets averaging 100–170 characters. Options: 4 bullets for older selected roles, a
  ~150-character bullet guide, make compact the default theme, or wait for the UI page-fit controls.
- **Android downplay may be too strong.** The Quantum Base spec asks for "native Android (Kotlin)", yet the output
  never says "Android": it answers with "Kotlin and cross-platform integration". Is that the intent, or should the
  rule ensure a requirement on a downplayed topic is named once?

## Log

- 2026-10-21 · Step 1 · Drafted `docs/cv-source-format.md`. Chose markdown without YAML (D1) because `skills_raw`
  YAML is already invalid and the stdlib has no YAML parser.
- 2026-10-21 · Step 2 · Converted the PDF to `input/CV.v2.md`. Merged in the Boostworks role from `input/CV.md`.
  Flagged source oddities in comments (grade count, GScript, NSProtocol). A throwaway stdlib probe parsed it cleanly:
  20 roles, all dated.
- 2026-10-21 · Step 3 · Review answers: elided text is context for the model, not stripped (D3, reverses the draft);
  quotes are plain text (D4); contact links on by default via a directive (D8); keep the current earlier-career
  format (D9); the three `TODO` titles became "Freelance"; dates are `Mon YYYY` (D7). Added D6 (themes, no
  hard-coded styles) and D10 (Claude Code backend next). Page fit and directive toggles deferred to the UI.
- 2026-10-21 · Step 4 · Added `backends/claudecode/` + `run_claudecode_attempt` (`claude -p`, prompt on stdin, JSON
  output, run from a temp dir with `--tools "" --safe-mode --no-session-persistence --system-prompt`; parent
  `CLAUDECODE*` env vars stripped). Default model `opus`. 10 new tests (fake `claude` on PATH); 43/43 pass. Docs:
  backends.md, README, architecture.md, gaps.md. Baseline: the existing output was **Gemini 2.5 Flash**, not Copilot
  (saved to `output/baseline-gemini-2.5-flash/`). Opus passed validation first time in 45s (~$0.20 list-price
  equivalent, which counts against the subscription). Both are 2 pages and ~1,300 words. Opus grounds each
  requirement in a named role (Jenkins attributed to Actual Experience, where Gemini claimed "CI/CD & Jenkins
  Specialist") and drops filler ("Fluent English"). Opus flaws: an uppercase "1996 - MAY 2023" intro, and This One
  moved to earlier career. Both of these the v2 contract addresses (computed date span, three-letter months).
- 2026-10-21 · Planning · Added D11 (steering via `input/steering.md`, file only and no UI yet; wired in step 8,
  prompt rule in step 7) and D12 (Copilot comparison deferred to the new step 11). Widened step 7 to replace the
  stale `prompt.md` input contract. Added a Handoff section ahead of a new session.
- 2026-10-21 · Step 5 · Added `cv_source.py` (parse → dict, `prompt_text`, elided items by scope, directives, linter,
  `--lint`/`--json` CLI) and `tests/test_cv_source.py` (20 tests; full suite 63/63). `input/CV.v2.md` lints with 0
  errors, 0 warnings and 3 info (the overlaps already flagged in its comments); the old `input/CV.md` fails, as
  expected. Spec finalised (banner removed, parser section added); the import rules moved to
  `input/import_prompt.md`, which the spec now points to, rather than living in both. D3/D4 wording needed no change.
  Docs: AGENTS.md, architecture.md, gaps.md.
- 2026-10-21 · Step 6 spike · Prototyped semantic fenced divs, a Lua filter and a theme dict in the scratchpad
  against `output/tailored.md`. Rendered PNGs match today's apart from three differences: tidier spacing
  ("(AppStore)", "LinkedIn | GitHub"; today's raw-Typst joins add stray spaces), the page-number size (the global 9pt
  reaches the footer), and the education title bold (left out of the prototype). DOCX custom styles work for
  paragraphs and spans but not for lists. Paused for the user's call on the DOCX theme form.
- 2026-10-21 · Step 6 review · User approved the spike. DOCX styling goes in a text `themes/docx-styles.xml`
  because PDF is the primary format (D13). The tidier spacing is accepted (D14), and DOCX keeps today's look for
  now.
- 2026-10-21 · Step 6 · Rewrote `apply_semantic_tag_formatting` to emit semantic markup only, with one export file
  for both formats (`tailored.docx.export.md` dropped, also from `ALLOWED_OUTPUT_FILES`). Added `themes/` and
  `--theme`/`CV_THEME`. Requirement items became one `requirements-list` div; the theme draws its items as the old
  bullet tables. PNG diff against the old render: page 2 identical; page 1 differs only in the D14 spacing plus 9
  anti-aliasing pixels. Both renders are 2 pages, and compact is also 2 on this CV. The DOCX now puts the title and
  contact lines in separate paragraphs (the old output merged them into one). Added
  `tests/test_cv_convert.py` (17 tests; 80/80 pass). Docs: cv-format.md §5, architecture.md, gaps.md, AGENTS.md.
- 2026-10-21 · Step 7 · Rewrote `input/prompt.md` as v2: the input contract describes the source format, RUN FACTS and
  steering; the output contract is values-only. New validator (D7 date normalisation, bold lead-ins, list lengths per
  the gap table, optional `role_cutoff`) and renderer (fixed requirements heading, computed earlier span, `directives`
  for contact links and omitted keywords). New tags and styles: `candidate-subheader`, `earlier-intro`,
  `earlier-title`, `earlier-company`, `skills-group`, plus PDF and DOCX theme entries. v1 bullet tags still render. Calls
  made without asking: D15–D17. Added `tests/test_generate_cv.py` (21 tests) and v2 cases in `test_cv_convert`;
  102/102 pass. Render check (no LLM call): the last Opus v1 JSON, mapped by hand to v2, renders to a 2-page PDF that
  looks like the step 6 render. Docs: cv-format.md §1–5, gaps.md, AGENTS.md.
- 2026-10-21 · Step 7 review · User approved D15 and D16. D17 revised: a cutoff breach is now a warning
  (`warnings` list through `parse_and_validate_json_output`, printed by `main`), and in general misbehaving runs
  warn rather than fail when the output still renders. D18: the earlier-career intro span is years only. 102/102 pass.
- 2026-10-21 · Step 8 · Wired `generate_cv.main`: parse and lint (errors stop the run, D19), `--cv`, RUN FACTS, steering
  (D11), `role_cutoff`, directives, elision check (`find_elision_leaks`: strict for entries/bullets/field values,
  phrases from 3 words), page count from the root page tree, and warnings plus `page_count`/`steering` recorded in
  `tailored.model.json`. The first live Opus run on `CV.v2.md` failed validation on `Dates: 2016` copied verbatim, so
  single-point dates are now valid (D19). The second run passed: 5 selected roles, all after the cutoff, 3 pages
  (warning shown). Found that `.env` fast mode truncates the v2 CV (gaps.md). 14 new tests; 116/116 pass. Docs:
  cv-format.md §2–3, architecture.md, AGENTS.md, gaps.md.
- 2026-10-21 · Step 9 (swap) · User turned fast mode off. `git mv` moved `CV.md` to `CV.v1.md` and `CV.v2.md` to `CV.md`,
  and references were updated (cv-format.md §1 now points to the source-format spec, plus cv-source-format.md,
  gaps.md and the `test_cv_source` fixture). The UI server had been running since before step 4 and showed Claude
  Code as disabled ("module load failed"); `/api/server/restart` fixed it. 116/116 pass. Comparison not run yet.
- 2026-10-21 · Step 9 (comparison) · Fast mode confirmed off. Opus on `CV.md` passed first time in 60s, but is still
  3 pages (1,414 words against Gemini's 1,030). Overflow is contract-driven: 15 earlier roles (rule 12) and 8 skill
  groups. Education now includes the degree. Quality is good: every requirement is grounded in a named role, all
  selected roles fall after the cutoff, and the headline uses held titles. Found that the job spec had changed
  (uncommitted, Quantum Base), so the comparison with the Kodly-based baselines is not like-for-like. Kept step 8
  output in `output/step8-opus-fastmode/`. Page fit raised as an open question; no code changed.
- 2026-10-21 · Step 9 (page fit) · User's calls: cap earlier career and skill groups (D20), weight Android down and AI
  tooling up as swappable weightings (D21), serial comma (D22), no Kodly rerun. Weightings are `Emphasise`/`Downplay`
  directives in `input/CV.md` plus one generic prompt rule, not topic-specific prompt text. Caps warn (D17). 3 new
  tests; 119/119 pass. Live Opus run: within the caps, but still 3 pages (13 lines over; compact fits 2). Android 6→0
  mentions, AI 16→21. Docs: cv-source-format.md, cv-format.md §2–3.
- 2026-10-21 · Formatting and UI (user requests, outside the step list) · Professional Summary and Targeted
  Requirements are ragged-right (`summary-justify` in `themes/default.typ`; pandoc's template justifies everything).
  `cv_convert` merges consecutive summary points into one paragraph, keeping the bold lead-ins, so the UI's
  format-only path picks it up too. CV tab Theme picker: listed from `themes/*.typ` (`available_themes`, served in
  `/api/state`), saved in localStorage, re-runs formatting on change; full runs pass `--theme` to `generate_cv`.
  Checked via the API (compact 2 pages, default 3). Tests: 126 Python, 41 JS pass.
- 2026-10-21 · Steering UI (user request) · D23. Steering tab and checkbox (`steering-feature.js`), `steering` in
  full-run requests, `generate_cv --steering-file/--no-steering`, `outputs.steering` in `/api/state` for the 🧭
  title marker. Checked the command flags and state field without a model call; no steered run made yet. User
  checked the UI. Tests: 134 Python, 50 JS pass.
