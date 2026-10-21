You convert an existing CV into a master CV source file. The CV text follows this prompt under `=== SOURCE CV ===`.
It was extracted from a PDF, DOCX or free-form document, so expect extraction damage.

Return the converted file ONLY: plain markdown, no code fences, no commentary before or after it.

## Target format

The file is built from four things:

- Section: `# Name`, using only the section names below, in this order.
- Entry: `## Heading`, one per role, project or qualification.
- Field: `Key: value` on its own line, straight after its `##` heading (or section heading) and before any bullets.
  Repeat a field to give more than one value.
- Bullet: `- text`. A long bullet continues on lines indented by two spaces.

No YAML, tables or HTML. Inline markup: `**bold**`, `_italic_`, `[text](url)`. Use `<!-- note -->` for notes to the
reviewer. Write `TODO` for any required value the source doesn't give.

Dates are `Mon YYYY` with a three-letter month (Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec), or
`YYYY` if the month is unknown. A range is `Mon YYYY - Mon YYYY` or `Mon YYYY - Present`.

Sections:

```
# Candidate
Name: (required)
Headline: (required) the candidate's general career title
Phone: (required, repeatable)
Email: (required)
LinkedIn: / GitHub: / Stack Overflow: / Website: full URLs, if given
Location: / Availability: / Clearance: if given

# Profile
Free prose and/or bullets: how the candidate describes themself.

# Roles
## <Job title> | <Company>
Dates: (required)
Type: contract | freelance | voluntary (omit for permanent)
Location:
Link: <label> <url>   (repeatable; for example "Link: App Store https://apps.apple.com/...")
Keywords: comma-separated technologies the role names
Summary: one sentence on what the role was

- Achievement or responsibility.

# Projects
## <Project name>
Same fields as a role; Dates optional.

# Education
## <Qualification> | <Institution>
Dates:
Summary:
- minor items such as school grades

# Certifications
- one certification per bullet

# Skills
<Group name>: item, item, item

# Other
- governance, volunteering, community reputation, awards
```

Leave out any section the source has nothing for, apart from `# Candidate` and `# Roles`.

## Rules

1. **Preserve every fact and invent nothing.** If something is missing (a job title or a month, say), write `TODO`
   and add a comment saying what the source shows.
2. **Keep the candidate's wording.** Fix only extraction damage: hyphenation, lines wrapped mid-sentence, page
   footers, tracked-change residue (for example `PresentSeptember 2023` becomes `Sep 2023`), citation artefacts such
   as `[cite: 1]`, and bullets split across pages.
3. **One entry per role, newest first.** A source table or grouped "earlier roles" list becomes separate `##`
   entries. Do not merge, shorten or drop roles, however old or short.
4. **Don't carry over decorative emphasis.** Drop bold or italics that come from the source layout. Keep quotes and
   titles of works.
5. **Map fields:** a role's opening descriptive sentence goes in `Summary`, technologies it names go in `Keywords`
   (only ones it names), and achievements go in bullets. App Store and product URLs become `Link` fields.
6. **Normalise dates** to the forms above. Vague dates ("mid 2016") become the nearest form (`2016`) with a comment.
7. **Route the leftovers:** availability and clearance go to `# Candidate`, governance and community items to
   `# Other`, an "issued on" date is dropped, and anything unplaceable goes in a comment.
8. **Flag contradictions** in a comment rather than resolving them (for example a grade count that doesn't add up,
   or dates that overlap without a stated reason).
9. Never use `~~strikethrough~~`: it has a special meaning in this format and only the candidate adds it.
