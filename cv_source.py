"""
Architecture role:
- Layer: input parsing (master CV source format).
- Responsibility: parse `input/CV.md` in the format described in docs/cv-source-format.md into a plain dict,
    produce the comment-stripped text sent to the model, collect elided phrases for the post-generation check,
    and lint the file.

Plain-language purpose:
- Stdlib-only reader and checker for the master CV, so malformed input is caught before any model call.
- `python3 cv_source.py --lint [path]` prints issues; `--json` dumps the parsed dict.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CV_PATH = Path("input/CV.md")

ERROR = "error"
WARNING = "warning"
INFO = "info"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ROLE_TYPES = ("permanent", "contract", "freelance", "voluntary")
CONTACT_LINK_KEYS = ("linkedin", "github", "stack overflow", "website")

ENTRY_FIELDS = {
    "dates": False,
    "type": False,
    "location": False,
    "link": True,
    "keywords": False,
    "summary": False,
}

# Section key -> layout. "fields" maps known keys to whether they repeat (None: any key is allowed and
# each key appears once). "entries" sections hold `##` entries with ENTRY_FIELDS-style fields.
SECTIONS = {
    "candidate": {
        "layout": "fields",
        "fields": {
            "name": False,
            "headline": False,
            "phone": True,
            "email": False,
            "linkedin": False,
            "github": False,
            "stack overflow": False,
            "website": False,
            "subheader": True,
            "location": False,
            "availability": False,
            "clearance": False,
        },
        "required": ("name", "headline", "phone", "email"),
    },
    "profile": {"layout": "prose"},
    "roles": {"layout": "entries", "fields": ENTRY_FIELDS, "required": ("dates",)},
    "projects": {"layout": "entries", "fields": ENTRY_FIELDS, "required": ()},
    "education": {"layout": "entries", "fields": {"dates": False, "summary": False}, "required": ()},
    "certifications": {"layout": "bullets"},
    "skills": {"layout": "fields", "fields": None, "required": ()},
    "other": {"layout": "bullets"},
    "directives": {
        "layout": "fields",
        "fields": {"omit": False, "contact links": False},
        "required": (),
    },
}
REQUIRED_SECTIONS = ("candidate", "roles")

COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
SECTION_RE = re.compile(r"^#\s+(.+?)\s*$")
ENTRY_RE = re.compile(r"^##\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^-\s+(.*)$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 &/()+.,'-]{0,39}?)\s*:\s*(.*)$")
ELIDED_RE = re.compile(r"~~(.+?)~~")
WHOLE_ELIDED_RE = re.compile(r"^~~(.+)~~$")
TODO_RE = re.compile(r"\bTODO\b")
DATE_POINT_RE = re.compile(r"^(?:([A-Z][a-z]{2})\s+)?(\d{4})$")
DATE_SEPARATOR_RE = re.compile(r"\s+[-–]\s+")
URL_RE = re.compile(r"^https?://\S+$")


def strip_comments(text: str) -> tuple[list[str], set[int]]:
    """Remove `<!-- -->` comments, keeping line numbering.

    Returns:
    - The lines with comments removed (comment newlines preserved so indices still match the file).
    - Zero-based indices of lines that held only a comment (and whitespace); callers skip these entirely.
    """
    comment_lines: set[int] = set()

    def replace(match: re.Match) -> str:
        start_line = text.count("\n", 0, match.start())
        for offset in range(match.group(0).count("\n") + 1):
            comment_lines.add(start_line + offset)
        return "\n" * match.group(0).count("\n")

    lines = COMMENT_RE.sub(replace, text).split("\n")
    comment_only = {index for index in comment_lines if index < len(lines) and not lines[index].strip()}
    return lines, comment_only


def prompt_text(text: str) -> str:
    """Return the source as sent to the model: comments and comment-only lines removed, blank runs collapsed."""
    lines, comment_only = strip_comments(text)
    kept = [line.rstrip() for index, line in enumerate(lines) if index not in comment_only]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip() + "\n"


def parse_date_point(value: str) -> str | None:
    """Parse `Mon YYYY` or `YYYY` into `YYYY-MM` or `YYYY`. Returns None when the form is invalid."""
    match = DATE_POINT_RE.match(value.strip())
    if not match:
        return None
    month, year = match.groups()
    if month is None:
        return year
    if month not in MONTHS:
        return None
    return f"{year}-{MONTHS.index(month) + 1:02d}"


def parse_dates(value: str) -> dict | None:
    """Parse a `Dates:` value into `{"start": "YYYY[-MM]", "end": "YYYY[-MM]" | "present" | None}`.

    Boundaries:
    - Accepts `Mon YYYY`, `YYYY` or a range of them separated by a spaced hyphen or en dash; `Present` only as the end.
    - Returns None for anything else, including an end before its start.
    """
    parts = DATE_SEPARATOR_RE.split(value.strip())
    if len(parts) not in (1, 2):
        return None
    start = parse_date_point(parts[0])
    if start is None:
        return None
    if len(parts) == 1:
        return {"start": start, "end": None}
    if parts[1].strip().lower() == "present":
        return {"start": start, "end": "present"}
    end = parse_date_point(parts[1])
    if end is None or end[:4] < start[:4] or (len(end) == len(start) == 7 and end < start):
        return None
    return {"start": start, "end": end}


def _unwrap_elided(text: str) -> tuple[str, bool]:
    match = WHOLE_ELIDED_RE.match(text.strip())
    if match and "~~" not in match.group(1):
        return match.group(1).strip(), True
    return text, False


def _new_entry(heading: str, line: int) -> dict:
    heading, elided = _unwrap_elided(heading)
    title, _, subtitle = (part.strip() for part in heading.partition("|"))
    return {
        "heading": heading,
        "title": title,
        "subtitle": subtitle,
        "line": line,
        "elided": elided,
        "fields": {},
        "elided_fields": [],
        "bullets": [],
    }


def _new_section(title: str, line: int) -> dict:
    return {
        "title": title,
        "line": line,
        "known": title.lower() in SECTIONS,
        "fields": {},
        "elided_fields": [],
        "bullets": [],
        "prose": [],
        "entries": [],
    }


def parse_cv_source(text: str) -> dict:
    """Parse CV source markdown into a plain dict.

    Returns:
    - `sections`: lowercased section name -> `{title, line, known, fields, elided_fields, bullets, prose, entries}`.
      `fields` maps lowercased keys to lists of values (repeatable keys keep every value). Each entry is
      `{heading, title, subtitle, line, elided, fields, elided_fields, bullets}`; `title`/`subtitle` split the
      heading on `|`. Bullets are `{text, line, elided}`. Values keep their inline markup.
    - `directives`: `{"omit": [...], "contact_links": bool}` with defaults applied.
    - `elided`: every elided phrase, `{text, line, scope}` (scope: phrase, field, bullet or entry).
    - `todos`: `{line, text}` for each line containing `TODO`.
    - `issues`: structural problems found while parsing (see `lint_cv_source` for the full check).
    - `prompt_text`: the text sent to the model.

    Boundaries:
    - Comments are dropped first; elided text is kept in values (the model sees it as context).
    - Never raises on malformed input; problems become issues.
    """
    lines, comment_only = strip_comments(text)
    doc: dict = {"sections": {}, "elided": [], "todos": [], "issues": []}
    section: dict | None = None
    entry: dict | None = None
    last_bullet: dict | None = None

    def issue(level: str, line: int, message: str) -> None:
        doc["issues"].append({"level": level, "line": line, "message": message})

    for index, raw in enumerate(lines):
        if index in comment_only:
            continue
        line_no = index + 1
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            last_bullet = None
            continue

        if stripped.count("~~") % 2:
            issue(WARNING, line_no, "unmatched ~~ (elision marker)")
        if TODO_RE.search(stripped):
            doc["todos"].append({"line": line_no, "text": stripped})

        # A continuation keeps its bullet's line for whole-bullet elision; phrases are collected per line.
        if last_bullet is not None and line.startswith("  ") and not BULLET_RE.match(stripped):
            last_bullet["text"] += " " + stripped
            _collect_phrases(doc, stripped, line_no)
            continue
        last_bullet = None

        if match := ENTRY_RE.match(line):
            if section is None:
                issue(WARNING, line_no, "entry before any # section; ignored")
                continue
            entry = _new_entry(match.group(1), line_no)
            section["entries"].append(entry)
            if entry["elided"]:
                doc["elided"].append({"text": entry["heading"], "line": line_no, "scope": "entry"})
            else:
                _collect_phrases(doc, entry["heading"], line_no)
            continue

        if match := SECTION_RE.match(line):
            title = match.group(1)
            key = title.lower()
            if key in doc["sections"]:
                issue(ERROR, line_no, f"duplicate section '# {title}'")
            section = _new_section(title, line_no)
            doc["sections"].setdefault(key, section)
            entry = None
            continue

        if section is None:
            issue(WARNING, line_no, "text before any # section; ignored")
            continue

        target = entry if entry is not None else section
        layout = SECTIONS.get(section["title"].lower(), {}).get("layout", "prose")

        if match := BULLET_RE.match(stripped):
            body, elided = _unwrap_elided(match.group(1))
            last_bullet = {"text": body, "line": line_no, "elided": elided}
            target["bullets"].append(last_bullet)
            if elided:
                doc["elided"].append({"text": body, "line": line_no, "scope": "bullet"})
            else:
                _collect_phrases(doc, body, line_no)
            continue

        body, elided = _unwrap_elided(stripped)
        field = FIELD_RE.match(body) if layout != "prose" else None
        if field and not URL_RE.match(body):
            key, value = field.group(1).strip().lower(), field.group(2).strip()
            if target["bullets"]:
                issue(WARNING, line_no, f"field '{field.group(1)}' after bullets; fields go first")
            target["fields"].setdefault(key, []).append(value)
            if elided:
                target["elided_fields"].append(key)
                doc["elided"].append({"text": body, "line": line_no, "scope": "field"})
            else:
                _collect_phrases(doc, value, line_no)
            continue

        if layout != "prose" or entry is not None:
            issue(WARNING, line_no, "unexpected text; expected a 'Key: value' field or '- bullet'")
        section["prose"].append(stripped)
        _collect_phrases(doc, stripped, line_no)

    doc["directives"] = _directives(doc)
    doc["prompt_text"] = prompt_text(text)
    return doc


def _collect_phrases(doc: dict, text: str, line: int) -> None:
    for match in ELIDED_RE.finditer(text):
        doc["elided"].append({"text": match.group(1).strip(), "line": line, "scope": "phrase"})


def _directives(doc: dict) -> dict:
    fields = doc["sections"].get("directives", {}).get("fields", {})
    omit: list[str] = []
    for value in fields.get("omit", []):
        omit.extend(item.strip().lower() for item in value.split(",") if item.strip())
    contact_links = True
    for value in fields.get("contact links", []):
        contact_links = value.strip().lower() not in ("no", "false", "off")
    return {"omit": omit, "contact_links": contact_links}


def _lint_fields(issues: list, owner: str, line: int, fields: dict, spec: dict) -> None:
    known = spec.get("fields")
    for key, values in fields.items():
        if known is not None and key not in known:
            issues.append((WARNING, line, f"{owner}: unknown field '{key}'"))
        repeatable = known.get(key, False) if known is not None else False
        if len(values) > 1 and not repeatable:
            issues.append((WARNING, line, f"{owner}: field '{key}' given {len(values)} times; only the first is used"))
        if any(not value for value in values):
            issues.append((WARNING, line, f"{owner}: field '{key}' is empty"))
    for key in spec.get("required", ()):
        if key not in fields:
            issues.append((ERROR, line, f"{owner}: missing required field '{key.title()}'"))


def _lint_entry_values(issues: list, owner: str, entry: dict) -> None:
    fields = entry["fields"]
    line = entry["line"]
    for value in fields.get("dates", [])[:1]:
        if parse_dates(value) is None:
            issues.append(
                (ERROR, line, f"{owner}: bad Dates '{value}'; use 'Mon YYYY', 'YYYY' or a range ending in 'Present'")
            )
    for value in fields.get("type", [])[:1]:
        if value.lower() not in ROLE_TYPES:
            issues.append((WARNING, line, f"{owner}: Type '{value}' is not one of {', '.join(ROLE_TYPES)}"))
    for value in fields.get("link", []):
        label, _, url = value.rpartition(" ")
        if not label or not URL_RE.match(url):
            issues.append((WARNING, line, f"{owner}: Link '{value}' should be '<label> <url>'"))


def _date_end_key(parsed: dict) -> str:
    end = parsed["end"]
    if end == "present":
        return "9999-12"
    if end is None:
        end = parsed["start"]
    return end if len(end) == 7 else f"{end}-12"


def _lint_roles(issues: list, entries: list) -> None:
    dated = [(entry, parse_dates(entry["fields"]["dates"][0])) for entry in entries if entry["fields"].get("dates")]
    dated = [(entry, parsed) for entry, parsed in dated if parsed]
    for (newer, newer_dates), (older, older_dates) in zip(dated, dated[1:]):
        if older_dates["start"] > newer_dates["start"]:
            issues.append((WARNING, older["line"], f"role '{older['heading']}' starts after the role above it; list newest first"))
    for position, (entry, parsed) in enumerate(dated):
        start = parsed["start"] if len(parsed["start"]) == 7 else f"{parsed['start']}-01"
        for other, other_dates in dated[position + 1 :]:
            if _date_end_key(other_dates) > start:
                issues.append(
                    (INFO, entry["line"], f"role '{entry['heading']}' overlaps '{other['heading']}'")
                )
    for entry in entries:
        if not entry["subtitle"]:
            issues.append((WARNING, entry["line"], f"role '{entry['heading']}' has no '| Company' in its heading"))


def lint_cv_source(doc: dict) -> list[dict]:
    """Check a parsed CV against the source format.

    Returns:
    - Issues as `{level, line, message}` sorted by line. Levels: `error` (the pipeline can't rely on the file),
      `warning` (likely a mistake, or a `TODO` left in), `info` (worth a look, such as overlapping roles).
    """
    issues: list[tuple[str, int, str]] = [(item["level"], item["line"], item["message"]) for item in doc["issues"]]
    sections = doc["sections"]

    for key in REQUIRED_SECTIONS:
        if key not in sections:
            issues.append((ERROR, 1, f"missing required section '# {key.title()}'"))

    for key, section in sections.items():
        spec = SECTIONS.get(key)
        line = section["line"]
        if spec is None:
            issues.append((INFO, line, f"unknown section '# {section['title']}'; sent to the model as context"))
            continue
        layout = spec["layout"]
        if layout != "entries" and section["entries"]:
            issues.append((WARNING, section["entries"][0]["line"], f"'## ' entries are not used in '# {section['title']}'"))
        if layout == "entries" and (section["fields"] or section["bullets"]):
            issues.append((WARNING, line, f"'# {section['title']}' content must sit under '## ' entries"))
        if layout == "fields":
            if section["bullets"]:
                issues.append((WARNING, section["bullets"][0]["line"], f"bullets are not used in '# {section['title']}'"))
            _lint_fields(issues, f"# {section['title']}", line, section["fields"], spec)
        if layout == "bullets" and section["fields"]:
            issues.append((WARNING, line, f"fields are not used in '# {section['title']}'; use bullets"))
        for entry in section["entries"] if layout == "entries" else ():
            owner = f"'{entry['heading']}'"
            _lint_fields(issues, owner, entry["line"], entry["fields"], spec)
            _lint_entry_values(issues, owner, entry)

    candidate = sections.get("candidate", {}).get("fields", {})
    for key in CONTACT_LINK_KEYS:
        for value in candidate.get(key, []):
            if not URL_RE.match(value):
                issues.append((WARNING, sections["candidate"]["line"], f"# Candidate: '{key}' should be a full URL"))

    directives = sections.get("directives", {})
    for value in directives.get("fields", {}).get("contact links", []):
        if value.strip().lower() not in ("yes", "no", "true", "false", "on", "off"):
            issues.append((ERROR, directives["line"], f"Contact links: '{value}' should be yes or no"))
    for name in doc["directives"]["omit"]:
        if name not in ENTRY_FIELDS:
            issues.append((WARNING, directives["line"], f"Omit: '{name}' is not an entry field"))

    if "roles" in sections:
        _lint_roles(issues, sections["roles"]["entries"])

    for todo in doc["todos"]:
        issues.append((WARNING, todo["line"], f"TODO left in: {todo['text']}"))

    return [
        {"level": level, "line": line, "message": message}
        for level, line, message in sorted(set(issues), key=lambda item: (item[1], item[2]))
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and lint the master CV source (docs/cv-source-format.md)")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_CV_PATH), help="CV source file (default: input/CV.md)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--lint", action="store_true", help="print issues; exit 1 if any are errors")
    mode.add_argument("--json", action="store_true", help="print the parsed dict as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.path)
    doc = parse_cv_source(path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0

    issues = lint_cv_source(doc)
    for item in issues:
        print(f"{path}:{item['line']}: {item['level']}: {item['message']}")
    counts = {level: sum(1 for item in issues if item["level"] == level) for level in (ERROR, WARNING, INFO)}
    print(f"{counts[ERROR]} error(s), {counts[WARNING]} warning(s), {counts[INFO]} info", file=sys.stderr)
    return 1 if counts[ERROR] else 0


if __name__ == "__main__":
    sys.exit(main())
