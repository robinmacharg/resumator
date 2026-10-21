# CV formats

The CV exists in four forms, in this order: **input master CV** → **prompt** → **model JSON** → **tagged markdown**
→ PDF/DOCX.

## 1. Input master CV (`input/CV.md`)

This is a de facto format: nothing parses it except the LLM. Current layout:

```markdown
---                                  # YAML front matter
candidate: {name, title, location, phone, email, linkedin, github, stackoverflow, availability, clearance}
metadata: {target_roles: [..], last_updated: YYYY-MM-DD}
skills_raw: {status, <group>: [..], ...}   # free-form skills pool for the model to regroup
---
# Professional Summary               # prose paragraphs
---
# Current & Recent Experience
## <Role title> | <Company>
**Dates:** Month YYYY - Month YYYY|Present
**App Store:** <url>                 # optional; the prompt has rules to carry this through as app_store_url
**Keywords:** `[a, b, c]`
* achievement bullets
---
# Earlier Experience (Summary View)
## <Role> | <Company>
**Dates:** ... | **Location:** ...
*Summary:* one paragraph
## Earlier Engineering Roles         # bullets: **Role | Company** (*dates*): summary
---
# Open Source & Key Projects         # bullets: **Name:** desc ([link](url))
---
# Education, Certifications & Governance   # bullets
```

Notes:
- `---` separates sections, but the first pair is YAML front matter. Only the model reads this file, so there is no
  strict parsing.
- `input/prompt.md` (v2) already describes the v1 source format ([cv-source-format.md](cv-source-format.md)), which
  this file moves to at [plan](plans/cv-format-revamp.md) step 9.
- Hygiene issues in the current file are listed in [gaps.md](gaps.md).

## 2. Prompt assembly (`generate_cv.build_prompt`)

- If `prompt.md` contains `{cv_content}` or `{jobspec_content}`, it uses `str.format`. **Gotcha:** `prompt.md` contains
  literal JSON braces, so adding a placeholder makes `format` raise. Escape them as `{{ }}` or keep append mode.
- Otherwise (current behaviour) the prompt is `prompt.md` + `=== MASTER CV ===\n<cv>` + `=== JOB SPECIFICATION ===\n<spec>`.
- `CV_FAST_MODE=true` truncates the CV to its first 18,000 chars and appends `=== FAST MODE INSTRUCTIONS ===`.
- The v2 prompt also describes a `=== RUN FACTS ===` section (today, the selected-roles cutoff, directives) and an
  optional `=== CANDIDATE STEERING ===` section. `build_prompt` doesn't append either yet (plan step 8).

## 3. Model JSON contract (v2)

`prompt.md` defines the schema. `validate_and_normalize_payload(payload, role_cutoff=None, warnings=None)` enforces
it. A contract violation fails the run; a rule breach that still renders is appended to `warnings`, which `main`
prints (`output/tailored.model-output.txt` holds the raw text for debugging). JSON is extracted from
fenced or surrounding prose. The model supplies values only; headings, labels, fixed phrases and the earlier-career
date span come from the renderer.

| Path | Rule |
|---|---|
| top level | `candidate, document` required; `metadata` optional (free-form object, default `{}`). v1's `semantic_tags` and `skills_raw` are gone |
| `candidate` | `name, phone, email` non-empty; `linkedin, github, stackoverflow, website` http(s) or null; `subheader_lines` list (default `[]`). Other keys are dropped |
| `document.headline` | non-empty |
| `document.professional_summary` | 4–5 strings, each opening with `**bold phrase**` |
| `document.role_requirements` | `role_title` + `items` 4–6, each opening with `**bold phrase**` (a leading `- ` is stripped) |
| `document.education_credentials` | 1–3 |
| `document.selected_key_roles[]` | 1–5: `title`, `company`, `date_range`, `app_store_url` (http(s) or null), `keywords` ≥0, `bullets` 1–5. With `role_cutoff=(year, month)`, a start before the cutoff is a warning (a year-only start counts as December) |
| `document.earlier_career` | `sectors` ≥1 + `items[]` ≥1: `role_title, company, technologies` ≥0, `date_range` |
| `document.open_source_contributions` | 3–4 |
| `document.technical_skills[]` | ≥1 `{group, items ≥1}` |

- Date ranges are rewritten to D7 form by `normalize_date_range`: `Mon YYYY`, `YYYY` or `Present` either side of
  ` - `. Full or upper-case month names, en dashes and "to" are accepted. Ranges that end before they start fail.
- Bullet-like strings lose a leading `- `/`* ` (`clean_bullet_text`).
- Content rules (truthfulness, elision, no location, ~200-char summaries and so on) live only in the prompt. The
  elision check after generation is plan step 8.

## 4. Tagged markdown (`output/tailored.md`, `render_tagged_markdown`)

`render_tagged_markdown(payload, directives=None)` echoes `candidate` and `metadata` as YAML front matter, then writes
the body as lines prefixed with `[tag]` in a fixed section order. `directives` takes the `cv_source` shape
(`{omit, contact_links}`); by default everything prints.

1. `[candidate_name]`, `[candidate_title]` (the headline), `[candidate_contact]` (phone - email; then the
   LinkedIn/GitHub/StackOverflow/Website line unless `contact_links` is false), `[candidate_subheader]` ×N
2. `[section_heading] # Professional Summary` → `[summary_paragraph]` ×N
3. `[role_requirements_heading] ### Targeted Requirements Match for <role_title>` → `[role_requirements_item] - ...`
4. `# Education, Certifications & Credentials` → `[education_item] * ...`
5. `# Selected Key Roles` → per role: `[role_heading] ## Title | Company`, `[date_range] <dates> ([AppStore](url))`,
   `[keywords] Keywords: [..]` (skipped when empty or `omit` has `keywords`), `[role_bullet] * ...`
6. `# Earlier Career Highlights` → `[earlier_intro] **<YYYY> - <YYYY|Present>** Positions across <sectors>.` (span from
   `earlier_career_span`, years only), then `[earlier_role] * **Role** | _Company_ (tech) - dates`
7. `# Open Source Contributions` → `[project_item] * ...`
8. `# Technical Skills and Expertise` → `[skills_group] **Group** - a, b, c`

Section order and headings are hard-coded here. Reordering or renaming sections means changing this function.

## 5. Conversion (`cv_convert.py`)

- `apply_semantic_tag_formatting(text)` turns tags into **semantic markup only**: a pandoc fenced div
  `::: {custom-style="<name>"}` per styled line, or a `[…]{custom-style="<name>"}` span. It also does text
  clean-up (contact `tel:`/`mailto:` links, the `Dates:`/`Keywords:` labels, stray italics in summaries). Tag aliases
  are accepted (`name`, `summary`, `requirements_heading`/`_item`). Both the PDF and the DOCX compile from the one
  export file, `tailored.export.md` (front matter stripped).
- Style names: `candidate-name`, `candidate-title`, `candidate-contact`, `candidate-subheader`, `section-heading`,
  `summary-item`, `requirements-heading`, `requirements-list` (a div around the requirement bullets), `role-heading`,
  `date-range`, `keywords`, `earlier-intro`, and the spans `education-title`, `earlier-title`, `earlier-company` and
  `skills-group`. Role and project bullets and untagged lines are plain markdown. The v1 tags `bullet_primary` and
  `bullet_secondary` still render, so older `tailored.md` files convert.
- **Looks live in `themes/`, not code:**

| File | Role |
|---|---|
| `themes/styles.lua` | Pandoc Lua filter (Typst only): wraps each styled div/span in `#cv-style("<name>")[…]` |
| `themes/default.typ` | PDF theme, passed with `--include-before-body` (it must follow the template's `conf` rule, so not `-H`). `cv-theme` holds the sizes, margin and link colour; `cv-styles` maps each name to a look; unknown names render as body text. Also sets the page (margin, footer) and 9pt body text |
| `themes/compact.typ` | Preset layered after `default.typ`: overrides some `cv-theme` entries, then rebuilds `cv-style` and re-applies `cv-base` (Typst closures capture bindings when defined, so overriding the dict alone does nothing) |
| `themes/docx-styles.xml` | Word `<w:style>` entries merged into pandoc's default `reference.docx` at render time (`build_docx_reference` → `output/reference.docx`). DOCX is second-class: it keeps the pre-theme plain look. Lists can't take a custom style in DOCX, so bullets stay `Compact` |

- Choose a preset with `cv_convert.py --theme compact` or the `CV_THEME` env var. An unknown name warns and falls back
  to the default.
- PDF: `pandoc --pdf-engine=typst --lua-filter themes/styles.lua --include-before-body themes/<theme>.typ` (plain
  `pandoc` fallback, unstyled). DOCX: `pandoc --reference-doc`. The font is the first installed font from
  `CV_FONT_PRIORITY` (default `Calibri,Arial,Helvetica`).
- Checking a look change: render with `pandoc … -t typst -s` (same filter and theme), then
  `typst compile x.typ "x-{p}.png"` and `compare -metric AE` (ImageMagick) against a previous render.
