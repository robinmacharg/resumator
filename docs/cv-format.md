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
- The uncommitted "Input Contract" block in `input/prompt.md` describes `—` separators and `subsection:` labels. That
  does not match this layout. Align one with the other ([gaps.md](gaps.md)).
- Hygiene issues in the current file are listed in [gaps.md](gaps.md).

## 2. Prompt assembly (`generate_cv.build_prompt`)

- If `prompt.md` contains `{cv_content}` or `{jobspec_content}`, it uses `str.format`. **Gotcha:** `prompt.md` contains
  literal JSON braces, so adding a placeholder makes `format` raise. Escape them as `{{ }}` or keep append mode.
- Otherwise (current behaviour) the prompt is `prompt.md` + `=== MASTER CV ===\n<cv>` + `=== JOB SPECIFICATION ===\n<spec>`.
- `CV_FAST_MODE=true` truncates the CV to its first 18,000 chars and appends `=== FAST MODE INSTRUCTIONS ===`.
- There is no steering input yet ([gaps.md](gaps.md)).

## 3. Model JSON contract

`prompt.md` defines the schema. `validate_and_normalize_payload` enforces it, and any violation fails the run
(`output/tailored.model-output.txt` holds the raw text for debugging). JSON is extracted from fenced or surrounding
prose.

| Path | Rule |
|---|---|
| top level | `candidate, metadata, semantic_tags, skills_raw, document` required |
| `candidate` | `name, title, phone, email` non-empty; `linkedin, github, stackoverflow` optional |
| `semantic_tags` | the 14 keys in `REQUIRED_SEMANTIC_TAG_KEYS`, each value equal to its key |
| `document.professional_summary` | 4–5 strings, each starting with a `**bold phrase**` |
| `document.role_requirements` | `heading` + `items` 4–6 (`- **phrase:** ...`) |
| `document.education_credentials` | ≥2 strings |
| `document.selected_key_roles[]` | 1–5 items: `heading` ("Title \| Company"), `date_range` (month-year normalised), `app_store_url` (http(s) or null), `keywords` ≥1, `bullet_primary` ≥1, `bullet_secondary` ≥0 |
| `document.earlier_career` | `intro` + `items[]` ≥1: `role_title, company, technologies` ≥1, `date_range` |
| `document.open_source_contributions` | 3–5 |
| `document.technical_skills[]` | ≥1 `{group, items ≥1}` |
| `document.candidate_contact_lines` | optional extra contact lines |

Content rules (truthfulness, roles from the last 10 years only, no location, App Store link handling and so on) live
only in the prompt and are not validated.

## 4. Tagged markdown (`output/tailored.md`, `render_tagged_markdown`)

The JSON is echoed back as YAML front matter (`candidate, metadata, semantic_tags, skills_raw`). The body is then
written as lines prefixed with `[tag]` in a fixed section order:

1. `[candidate_name]`, `[candidate_title]`, `[candidate_contact]` (phone/email, then social links, then extra lines)
2. `[section_heading] # Professional Summary` → `[summary_paragraph]` ×N
3. `[role_requirements_heading] ### <dynamic>` → `[role_requirements_item] - ...`
4. `# Education, Certifications & Credentials` → `[education_item] * ...`
5. `# Selected Key Roles` → per role: `[role_heading] ## ...`, `[date_range] **Dates:** ... ([AppStore](url))`,
   `[keywords] **Keywords:** \`[..]\``, `[bullet_primary]`/`[bullet_secondary] * ...`
6. `# Earlier Career Highlights` → intro, then untagged `* **Role** | _Company_ (tech) - dates`
7. `# Open Source Contributions` → `[project_item] * ...`
8. `# Technical Skills and Expertise` → `**Group**` / `- a, b, c` (untagged)

Section order and headings are hard-coded here. Reordering or renaming sections means changing this function.

## 5. Conversion (`cv_convert.py`)

- `apply_semantic_tag_formatting(text, target="pdf"|"docx")` maps tags to output. For the PDF it emits raw Typst
  blocks (centred 18pt name, styled summary and requirement lines, links). For the DOCX it emits plain markdown. Tag
  aliases are accepted (`name`, `summary`, `requirements_heading`/`_item`).
- The front matter is stripped. The PDF gets a Typst `#set page(margin: 1.5cm)` header.
- PDF: `pandoc --pdf-engine=typst` (plain `pandoc` fallback). DOCX: `pandoc`. The font is the first installed
  font from `CV_FONT_PRIORITY` (default `Calibri,Arial,Helvetica`).
- Intermediates: `tailored.export.md` (PDF), `tailored.docx.export.md` (DOCX).
- Styling is in Python string templates. There is no separate template or theme file.
