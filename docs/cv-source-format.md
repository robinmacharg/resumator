# CV source format (v1)

> Agreed format ([plan](plans/cv-format-revamp.md)). `input/CV.md` moves to it at plan step 9; until then
> [cv-format.md §1](cv-format.md#1-input-master-cv-inputcvmd) describes the current file.

The master CV (`input/CV.md`) is the candidate's full record: every fact, nothing tailored. The generator selects,
orders and rewords for each job; this file never needs to look like the output. When in doubt, include it here and
let the generator drop it.

Worked example: [input/CV.v2.md](../input/CV.v2.md).

## Shape

Plain markdown built from four things:

| Element | Syntax | Used for |
|---|---|---|
| Section | `# Name` | One of the fixed section names below |
| Entry | `## Heading` | One role, project or qualification |
| Field | `Key: value` on its own line | Facts about the candidate or an entry |
| Bullet | `- text` | Achievements, responsibilities, list items |

- No YAML, tables or HTML (apart from comments). These parse with the Python stdlib and stay easy to hand-edit.
- A bullet continues onto indented lines (two or more spaces). A blank line or the next `-` ends it.
- Fields come straight after their `##` heading, before any bullets. Keys are case-insensitive.
- Repeat a field to give more than one value (for example two `Phone:` lines, or several `Link:` lines).
- Sections can appear in any order. A section with an unknown name goes to the model as background context.

## Inline markup

| Write | Meaning |
|---|---|
| `**bold**` | Bold. Kept wherever the generator reuses that text |
| `*italic*` or `_italic_` | Italic. Kept the same way |
| `"quoted phrase"` | Ordinary text: quotes need no escaping anywhere, including in field values |
| `[text](url)` | Link |
| `~~text~~` | **Elided**: context for the model, never output. Works on a phrase, a field, a bullet or a whole heading |
| `<!-- note -->` | Private note. Removed before the model sees the file |
| `TODO` | Unknown value. Never output; the linter lists them |

Elision examples:

```markdown
## ~~Principal iOS Developer | Amiosec Ltd.~~      ← the whole role is never output
~~Keywords: Xamarin, C#, EWS~~                     ← this role prints no keywords line
- ~~Mentored junior developers.~~                  ← one bullet held back
- Delivered for ~~three~~ flagship clients.        ← one phrase held back
```

The model sees elided text as background (it can inform tone or relevance) but must not print it. The prompt says
so, and after generation the code checks the output and flags any elided phrase that appears in it. Comments are the
only markup removed before prompting.

## Sections

### `# Candidate` (required)

Fields only.

| Field | Req. | Notes |
|---|---|---|
| `Name` | yes | |
| `Headline` | yes | Your general career title. The output headline is blended per job from this and your roles |
| `Phone` | yes | Repeatable. The first is used unless the job calls for another |
| `Email` | yes | |
| `LinkedIn`, `GitHub`, `Stack Overflow`, `Website` | no | Full URLs. Printed as one links line under phone/email (see `Contact links` directive) |
| `Subheader` | no | Repeatable. Extra lines printed in the subheader, in order (for example a portfolio line) |
| `Location` | no | Never printed in the contact line |
| `Availability` | no | For example "Open to permanent and contract; remote or hybrid" |
| `Clearance` | no | Security clearances and checks |

### `# Profile`

Free prose and/or bullets: how you describe yourself, recurring strengths, themes. Source material for the
professional summary. Facts that belong to a role go in the role instead.

### `# Roles` (required)

One `##` entry per role, newest first. Include every role, however old or short. The generator decides which are
"selected key roles" and which become one-line "earlier career" items.

```markdown
## <Job title> | <Company>
Dates: Mon YYYY - Mon YYYY            ← or "- Present"; "YYYY" alone if the month is unknown
Type: contract                         ← optional: permanent (default), contract, freelance, voluntary
Location: Bristol, UK                  ← optional
Link: App Store https://apps.apple.com/...   ← optional, repeatable: "<label> <url>"
Keywords: React Native, TypeScript, Fastlane
Summary: One sentence on what the role was.

- Achievement or responsibility.
- **Lead-in phrase:** detail, as you'd like it to read.
```

| Field | Req. | Notes |
|---|---|---|
| `Dates` | yes | `Mon YYYY` (three-letter month: Jan, Feb … Sep, Oct), `YYYY` if the month is unknown, or `Present`. Hyphen or en dash. Output uses the same forms |
| `Type` | no | Shown as "(Contract)" etc. where relevant |
| `Location` | no | |
| `Link` | no | First word is the label. `App Store` links are printed beside the dates |
| `Keywords` | no | Comma-separated skills used in the role. Commas inside `( )` don't split |
| `Summary` | no | One line. Short or old roles may have only this and no bullets |

### `# Projects`

Open source, side projects and publications. Same entry shape as roles; `Dates` is optional.

```markdown
## Bricksmith
Link: SourceForge http://bricksmith.sourceforge.net/
Keywords: Objective-C, C
Summary: SourceForge award-winning LEGO CAD for the Mac.
```

### `# Education`

One `##` entry per qualification: `## <Qualification> | <Institution>`, with optional `Dates` and `Summary`.
Bullets work for minor items (school grades and the like).

### `# Certifications`

Bullets, one certification each.

### `# Skills`

One field per group: `<Group name>: item, item, item`. Group names are yours; the generator regroups them for each job.

```markdown
Languages: Swift, Objective-C, Python (FastAPI, Flask), TypeScript
CI/CD: Fastlane, GitHub Actions, Azure Pipelines, Jenkins
```

### `# Other`

Bullets for anything else that might be relevant: governance, volunteering, community reputation, awards.

### `# Directives` (optional)

Fields that apply to every output generated from this CV.

| Field | Example | Effect |
|---|---|---|
| `Omit` | `Omit: keywords, location` | Never print these field types for any entry |
| `Contact links` | `Contact links: no` | Include (default) or leave out the LinkedIn/GitHub/Stack Overflow line |

Directives may later be set from the UI per run. This section holds the defaults.

## Parser and linter: `cv_source.py`

Stdlib only. Run from the repo root:

```bash
python3 cv_source.py --lint [path]   # issues as path:line: level: message; exit 1 on any error
python3 cv_source.py --json [path]   # the parsed dict
```

`parse_cv_source(text)` returns a dict:

| Key | Holds |
|---|---|
| `sections` | Lowercased section name → `{title, line, known, fields, elided_fields, bullets, prose, entries}` |
| `fields` | Lowercased key → list of values (every repeat kept). Values keep their inline markup, elided text included |
| `entries` | `{heading, title, subtitle, line, elided, fields, elided_fields, bullets}`; `title`/`subtitle` split the heading on `\|` |
| `bullets` | `{text, line, elided}`, continuation lines joined |
| `directives` | `{omit: [...], contact_links: bool}`, defaults applied |
| `elided` | Every elided item, `{text, line, scope}` with scope `entry`, `field`, `bullet` or `phrase` (for the post-generation check) |
| `todos` | `{line, text}` per line containing `TODO` |
| `prompt_text` | What the model gets: comments and comment-only lines removed, everything else as written |

`lint_cv_source(doc)` levels:

| Level | Examples |
|---|---|
| error | Missing `# Candidate` or `# Roles`, missing required field, bad `Dates`, duplicate section, bad `Contact links` value |
| warning | Unknown field, non-repeatable field repeated, field after bullets, stray text, roles not newest first, `\| Company` missing from a role heading, bad `Link`, unmatched `~~`, `TODO` left in |
| info | Unknown section (sent as context), overlapping roles |

## Importing an existing CV

The import rules and a compact copy of this format live in [input/import_prompt.md](../input/import_prompt.md), the
prompt an agent or the (later) import pipeline uses to convert a PDF, DOCX or free-form CV. Change the format here
and there together. Run `--lint` on the result before review.
