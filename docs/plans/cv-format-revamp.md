# Plan: CV format revamp

**Goal:** one human-editable, agent-friendly master CV format; rules for an agent to import any existing CV into it;
a revised generation contract whose output matches the target layout; and styling that lives in theme files rather
than in code.

**Status:** steps 1–4 done. Next: step 5 (formalise the source format).

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
| 4 | Claude Code backend: `backends/claudecode/module.py` (`claude -p`, JSON output, model selection, tools off) plus a smoke test. Baseline: run the current pipeline on Claude and compare with the Copilot `tailored_dev.pdf` | Second backend, baseline comparison | done |
| 5 | Formalise the source format: `cv_source.py` (stdlib parse → dict, strip comments, collect elided phrases, apply directives, lint required fields, date forms, `TODO`s and unknown keys) plus tests; finalise the spec; `input/import_prompt.md` from the import rules | Parser, linter, spec | todo |
| 6 | Styling: spike how pandoc carries named styles (fenced divs/spans with `custom-style`: DOCX supports them natively; Typst probably needs a small pandoc Lua filter mapping them to theme functions). Then move all current looks into `themes/default.typ` + `themes/reference.docx`, and add one compact preset | Theme files; `cv_convert` emits no styling | todo |
| 7 | Output contract v2: rewrite the `prompt.md` output section per the gap table; update `validate_and_normalize_payload` and `render_tagged_markdown` (semantic names from step 6); add tests for the validator and renderer | Revised contract | todo |
| 8 | Wire the pipeline: `generate_cv` parses the source, sends it (comments stripped) plus computed facts (today, 10-year cutoff, directives) to the model; elision check and page count after render (read the PDF's `/Pages /Count`; counting `/Type /Page` markers over-counts) | End-to-end run | todo |
| 9 | Swap in: replace `input/CV.md` with the reviewed v2 (back up the old one); run the full pipeline on both backends against the current job spec; compare | Real output | todo |
| 10 | Docs: update `cv-format.md`, `backends.md`, `gaps.md` (P2 schema/linter items resolved; P1 import narrowed), `AGENTS.md` | Docs in sync | todo |
| — | Later (UI): CV import (upload → extract → `import_prompt.md` → lint → review/replace); page-fit controls (theme preset or "compact" request); directive checkboxes | | later |

## Open questions

None outstanding. New ones go here as steps raise them.

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
