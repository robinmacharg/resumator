# CV source format (draft v1)

> **Status: draft for review** ([plan](plans/cv-format-revamp.md), step 1). Once agreed, this replaces
> [cv-format.md §1](cv-format.md#1-input-master-cv-inputcvmd).

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

## Importing an existing CV (rules for the agent)

When converting a PDF, DOCX or free-form CV into this format:

1. **Preserve every fact and invent nothing.** If something is missing (a job title or a month, say), write `TODO`
   and add a comment saying what the source shows.
2. **Keep the candidate's wording.** Fix only extraction damage: hyphenation, lines wrapped mid-sentence, page
   footers, tracked-change residue (for example `PresentSeptember 2023` becomes `Sep 2023`), citation artefacts such
   as `[cite: 1]`, and bullets split across pages.
3. **One entry per role.** A source table or grouped "earlier roles" list becomes separate `##` entries. Merging is
   the generator's job.
4. **Don't carry over decorative emphasis.** Drop bold or italics that come from the source layout. Keep quotes and
   titles of works.
5. **Map fields:** a role's opening descriptive sentence goes in `Summary`, technologies it names go in `Keywords`
   (only ones it names), and achievements go in bullets. App Store and product URLs become `Link` fields.
6. **Normalise dates** to `Mon YYYY`. Vague dates ("mid 2016") become the nearest form (`2016`) with a comment.
7. **Route the leftovers:** availability and clearance go to `# Candidate`, governance and community items to
   `# Other`, an "issued on" date is dropped, and anything unplaceable goes in a comment.
8. **Flag contradictions** in a comment rather than resolving them (for example a grade count that doesn't add up,
   or dates that overlap without a stated reason).
