"""
Architecture role:
- Layer: CV source text (pure functions, no DB, no I/O).
- Responsibility: three-way, entry-level merge of CV source files (docs/plans/multi-role.md R7, R11). Used by
    "Promote to master" (base = role's base master, ours = master, theirs = role) and "Pull from master"
    (base = role's base master, ours = role, theirs = master).

Plain-language purpose:
- Split a CV into units: the preamble, each `# Section` head (heading plus anything before its first `##`), and
    each `## Entry`. Sections without entries (Candidate, Profile, Skills, Directives…) are one unit each.
- Compare base, ours and theirs per unit, then rebuild the text from ours plus the changes the caller accepts.
- Units keep their raw text (comments, elisions, layout), so an untouched unit comes back byte for byte.

Boundaries:
- Headings are found the same way `cv_source.parse_cv_source` finds them, on comment-stripped lines, so a
    `# heading` inside `<!-- -->` doesn't split. Units are keyed by section and heading, case-insensitive, with
    `~~` elision unwrapped (eliding an entry is a change, not a removal plus an addition).
- A renamed heading is a removal plus an addition. Reordering on the theirs side is ignored; output order follows
    ours, with theirs' additions placed after their nearest preceding unit.
- Blank lines between units are normalised to one; trailing blank lines inside a unit are dropped.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from cv_source import ENTRY_RE, SECTION_RE, _unwrap_elided, strip_comments

PREAMBLE = "preamble"
SECTION = "section"
ENTRY = "entry"

# Classification of one unit across base / ours / theirs.
SAME = "same"  # ours == theirs (nothing to do)
OURS = "ours"  # only ours changed since base (kept, nothing to decide)
ADDED = "added"  # theirs added it
REMOVED = "removed"  # theirs removed it
CHANGED = "changed"  # theirs changed it
CONFLICT = "conflict"  # both sides changed it differently

# Resolutions for a conflict: keep ours, take theirs, or pass replacement text (None text = drop the unit).
KEEP_OURS = "ours"
TAKE_THEIRS = "theirs"


@dataclass(frozen=True)
class Unit:
    key: tuple[str, str]  # (section key, entry key); entry key "" for a section head, both "" for the preamble
    kind: str  # PREAMBLE, SECTION or ENTRY
    heading: str  # heading as written (without the leading `#`/`##`), "" for the preamble
    text: str  # raw lines, trailing blank lines removed, no trailing newline


@dataclass
class Change:
    key: tuple[str, str]
    kind: str
    heading: str
    status: str  # ADDED, REMOVED, CHANGED or CONFLICT
    base: str | None
    ours: str | None
    theirs: str | None

    @property
    def diff(self) -> str:
        """Unified diff from ours (or base, for additions) to theirs, for showing what changed in the unit."""
        before = self.ours if self.ours is not None else self.base
        return unit_diff(before, self.theirs)


@dataclass
class MergeResult:
    text: str
    changes: list[Change]  # every unit needing a decision, in output order
    applied: list[tuple[str, str]] = field(default_factory=list)  # keys whose theirs side (or resolution) was used
    unresolved: list[tuple[str, str]] = field(default_factory=list)  # conflicts left as ours


def _normalise(lines: list[str]) -> str:
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return "\n".join(line.rstrip() for line in lines)


def split_units(text: str) -> list[Unit]:
    """Split CV source text into ordered units. Empty preamble is omitted; duplicate keys get a `#2`, `#3`… suffix."""
    raw_lines = text.split("\n")
    clean_lines, comment_only = strip_comments(text)
    starts: list[tuple[int, str, str]] = []  # (line index, kind, heading)
    for index, line in enumerate(clean_lines):
        if index in comment_only:
            continue
        line = line.rstrip()
        if match := ENTRY_RE.match(line):
            starts.append((index, ENTRY, match.group(1)))
        elif match := SECTION_RE.match(line):
            starts.append((index, SECTION, match.group(1)))

    units: list[Unit] = []
    seen: dict[tuple[str, str], int] = {}
    preamble = _normalise(raw_lines[: starts[0][0]] if starts else raw_lines).strip("\n")
    if preamble.strip():
        units.append(Unit(("", ""), PREAMBLE, "", preamble))

    section_key = ""
    for position, (index, kind, heading) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(raw_lines)
        name = _unwrap_elided(heading)[0].strip().lower()
        key = _dedupe(seen, (name, "") if kind == SECTION else (section_key, name))
        if kind == SECTION:
            section_key = key[0]
        units.append(Unit(key, kind, heading, _normalise(raw_lines[index:end])))
    return units


def _dedupe(seen: dict[tuple[str, str], int], key: tuple[str, str]) -> tuple[str, str]:
    count = seen.get(key, 0) + 1
    seen[key] = count
    if count == 1:
        return key
    section, entry = key
    return (section, f"{entry}#{count}") if entry else (f"{section}#{count}", "")


def join_units(units: list[Unit]) -> str:
    """Rebuild CV text from units: one blank line between units, one trailing newline."""
    return "\n\n".join(unit.text for unit in units) + "\n" if units else ""


def unit_diff(before: str | None, after: str | None) -> str:
    """Line diff of one unit (unified format, no file headers)."""
    lines = difflib.unified_diff(
        (before or "").split("\n") if before is not None else [],
        (after or "").split("\n") if after is not None else [],
        lineterm="",
        n=2,
    )
    return "\n".join(line for line in lines if not line.startswith(("---", "+++")))


def classify(base: str | None, ours: str | None, theirs: str | None) -> str:
    """Classify one unit's texts (None = absent) from the point of view of applying theirs onto ours."""
    if ours == theirs:
        return SAME
    if base == theirs:
        return OURS
    if base == ours:
        if base is None:
            return ADDED
        return REMOVED if theirs is None else CHANGED
    return CONFLICT


def compare(base: str, ours: str, theirs: str) -> list[Change]:
    """Every unit that needs a decision (theirs-side changes and conflicts), in ours order then theirs additions."""
    base_units, our_units, their_units = (_by_key(split_units(text)) for text in (base, ours, theirs))
    changes = []
    for key in _union_order(our_units, their_units, base_units):
        b, o, t = (units.get(key) for units in (base_units, our_units, their_units))
        status = classify(*(unit.text if unit else None for unit in (b, o, t)))
        if status in (SAME, OURS):
            continue
        sample = t or o or b
        changes.append(
            Change(key, sample.kind, sample.heading, status, b and b.text, o and o.text, t and t.text)
        )
    return changes


def default_accept(changes: list[Change]) -> set[tuple[str, str]]:
    """Keys ticked by default: additions and changes from theirs. Removals and conflicts need a decision (R7)."""
    return {change.key for change in changes if change.status in (ADDED, CHANGED)}


def merge(
    base: str,
    ours: str,
    theirs: str,
    accept: set[tuple[str, str]] | None = None,
    resolutions: dict[tuple[str, str], str | None] | None = None,
) -> MergeResult:
    """Apply accepted theirs-side changes and conflict resolutions onto ours.

    Arguments:
    - `accept`: keys of ADDED/REMOVED/CHANGED units to take from theirs (default: `default_accept`). Others stay as ours.
    - `resolutions`: conflict key -> `KEEP_OURS`, `TAKE_THEIRS` or replacement text (`None` drops the unit).
      Conflicts without a resolution keep ours and are listed in `unresolved`.

    Returns a `MergeResult` with the rebuilt text. Units only ours changed are always kept.
    """
    base_units, our_units, their_units = (_by_key(split_units(text)) for text in (base, ours, theirs))
    changes = compare(base, ours, theirs)
    accept = default_accept(changes) if accept is None else set(accept)
    resolutions = resolutions or {}

    result: dict[tuple[str, str], Unit | None] = dict(our_units)
    applied, unresolved = [], []
    for change in changes:
        their_unit = their_units.get(change.key)
        if change.status == CONFLICT:
            if change.key not in resolutions:
                unresolved.append(change.key)
                continue
            choice = resolutions[change.key]
            if choice == KEEP_OURS:
                continue
            if choice == TAKE_THEIRS:
                result[change.key] = their_unit
            elif choice is None:
                result[change.key] = None
            else:
                result[change.key] = Unit(change.key, change.kind, change.heading, choice.rstrip())
            applied.append(change.key)
        elif change.key in accept:
            result[change.key] = their_unit
            applied.append(change.key)

    order = _union_order(our_units, their_units, base_units)
    units = [result[key] for key in order if result.get(key) is not None]
    return MergeResult(join_units(units), changes, applied, unresolved)


def _by_key(units: list[Unit]) -> dict[tuple[str, str], Unit]:
    return {unit.key: unit for unit in units}


def _union_order(*sides: dict[tuple[str, str], Unit]) -> list[tuple[str, str]]:
    """Keys in the first side's order; keys only in later sides go after their nearest preceding known key."""
    order = list(sides[0])
    for side in sides[1:]:
        previous: tuple[str, str] | None = None
        for key in side:
            if key not in order:
                position = order.index(previous) + 1 if previous is not None else _first_position(order, key)
                order.insert(position, key)
            previous = key
    return order


def _first_position(order: list[tuple[str, str]], key: tuple[str, str]) -> int:
    # Nothing precedes the key on its own side: put it first, after a preamble if there is one.
    return 1 if order and order[0] == ("", "") and key != ("", "") else 0
