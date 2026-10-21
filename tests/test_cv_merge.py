import unittest

from cv_merge import (
    ADDED,
    CHANGED,
    CONFLICT,
    ENTRY,
    KEEP_OURS,
    OURS,
    PREAMBLE,
    REMOVED,
    SAME,
    SECTION,
    TAKE_THEIRS,
    classify,
    compare,
    default_accept,
    join_units,
    merge,
    split_units,
    unit_diff,
)
from cv_source import lint_cv_source, parse_cv_source

BASE = """<!-- master CV -->

# Candidate
Name: Ada Lovelace
Headline: Engineer
Phone: 01234
Email: ada@example.com

# Profile
Careful with numbers.

# Roles

## Analyst | Engine Co
Dates: Jan 2020 - Present

- Wrote the first program.

## Translator | Menabrea
Dates: Jan 2018 - Dec 2019

- Translated the paper.
<!-- ## Not a heading -->

# Skills
Languages: Maths
"""


def edit(text: str, old: str, new: str) -> str:
    assert old in text, old
    return text.replace(old, new, 1)


ANALYST = ("roles", "analyst | engine co")
TRANSLATOR = ("roles", "translator | menabrea")


class SplitUnitsTests(unittest.TestCase):
    def test_units_and_keys(self) -> None:
        units = split_units(BASE)
        self.assertEqual(
            [unit.key for unit in units],
            [("", ""), ("candidate", ""), ("profile", ""), ("roles", ""), ANALYST, TRANSLATOR, ("skills", "")],
        )
        self.assertEqual([unit.kind for unit in units][:2], [PREAMBLE, SECTION])
        self.assertEqual(units[4].kind, ENTRY)
        self.assertEqual(units[4].heading, "Analyst | Engine Co")

    def test_commented_heading_does_not_split(self) -> None:
        translator = split_units(BASE)[5]
        self.assertIn("<!-- ## Not a heading -->", translator.text)

    def test_round_trip_is_exact_for_normalised_text(self) -> None:
        self.assertEqual(join_units(split_units(BASE)), BASE)

    def test_elided_heading_keeps_its_key(self) -> None:
        text = edit(BASE, "## Translator | Menabrea", "## ~~Translator | Menabrea~~")
        self.assertIn(TRANSLATOR, [unit.key for unit in split_units(text)])

    def test_duplicate_headings_get_suffixes(self) -> None:
        text = BASE + "\n## Analyst | Engine Co\nDates: 2017\n\n# Skills\nTools: Loom\n"
        keys = [unit.key for unit in split_units(text)]
        self.assertIn(("skills", "analyst | engine co"), keys)
        self.assertIn(("skills#2", ""), keys)

    def test_empty_and_preamble_only(self) -> None:
        self.assertEqual(split_units(""), [])
        self.assertEqual([unit.kind for unit in split_units("just text\n")], [PREAMBLE])
        self.assertEqual(join_units([]), "")


class ClassifyTests(unittest.TestCase):
    def test_statuses(self) -> None:
        self.assertEqual(classify("a", "a", "a"), SAME)
        self.assertEqual(classify("a", "b", "b"), SAME)
        self.assertEqual(classify(None, None, None), SAME)
        self.assertEqual(classify("a", "b", "a"), OURS)
        self.assertEqual(classify("a", None, "a"), OURS)
        self.assertEqual(classify(None, None, "a"), ADDED)
        self.assertEqual(classify("a", "a", None), REMOVED)
        self.assertEqual(classify("a", "a", "b"), CHANGED)
        self.assertEqual(classify("a", "b", "c"), CONFLICT)
        self.assertEqual(classify("a", None, "c"), CONFLICT)
        self.assertEqual(classify(None, "b", "c"), CONFLICT)


class MergeTests(unittest.TestCase):
    def test_no_changes_returns_ours(self) -> None:
        result = merge(BASE, BASE, BASE)
        self.assertEqual(result.text, BASE)
        self.assertEqual(result.changes, [])

    def test_ours_only_edits_survive(self) -> None:
        ours = edit(BASE, "Careful with numbers.", "Careful with numbers and looms.")
        self.assertEqual(merge(BASE, ours, BASE).text, ours)

    def test_theirs_change_applies_by_default(self) -> None:
        theirs = edit(BASE, "- Wrote the first program.", "- Wrote the first published program.")
        result = merge(BASE, BASE, theirs)
        self.assertEqual(result.text, theirs)
        self.assertEqual([(c.key, c.status) for c in result.changes], [(ANALYST, CHANGED)])
        self.assertEqual(result.applied, [ANALYST])

    def test_unaccepted_change_is_left_out(self) -> None:
        theirs = edit(BASE, "- Wrote the first program.", "- Wrote the first published program.")
        self.assertEqual(merge(BASE, BASE, theirs, accept=set()).text, BASE)

    def test_removal_is_unticked_by_default(self) -> None:
        # Promote: the role dropped an employer; the master must keep it unless asked (R7).
        role = edit(BASE, "## Translator | Menabrea\nDates: Jan 2018 - Dec 2019\n\n- Translated the paper.\n<!-- ## Not a heading -->\n\n", "")
        result = merge(BASE, BASE, role)
        self.assertEqual(result.text, BASE)
        self.assertEqual(result.changes[0].status, REMOVED)
        self.assertEqual(default_accept(result.changes), set())
        self.assertNotIn("Translator", merge(BASE, BASE, role, accept={TRANSLATOR}).text)

    def test_pull_keeps_role_removal_and_brings_master_edit(self) -> None:
        role = edit(BASE, "## Translator | Menabrea\nDates: Jan 2018 - Dec 2019\n\n- Translated the paper.\n<!-- ## Not a heading -->\n\n", "")
        master = edit(BASE, "Languages: Maths", "Languages: Maths, Poetry")
        result = merge(BASE, role, master)
        self.assertNotIn("Translator", result.text)
        self.assertIn("Languages: Maths, Poetry", result.text)
        self.assertEqual(result.unresolved, [])

    def test_added_entry_goes_after_its_predecessor(self) -> None:
        theirs = edit(BASE, "## Analyst | Engine Co", "## Engineer | Difference Ltd\nDates: Jan 2021 - Present\n\n## Analyst | Engine Co")
        theirs = edit(theirs, "Dates: Jan 2020 - Present", "Dates: Jan 2020 - Dec 2020")
        ours = edit(BASE, "Careful with numbers.", "Precise.")
        result = merge(BASE, ours, theirs)
        units = [unit.key for unit in split_units(result.text)]
        self.assertEqual(units[3:6], [("roles", ""), ("roles", "engineer | difference ltd"), ANALYST])
        self.assertIn("Precise.", result.text)
        self.assertIn("Dates: Jan 2020 - Dec 2020", result.text)

    def test_added_section_and_first_unit(self) -> None:
        theirs = "# Intro\nHello\n\n" + BASE.split("\n\n", 1)[1] + "\n# Other\n- Chess.\n"
        result = merge(BASE, BASE, theirs)
        keys = [unit.key for unit in split_units(result.text)]
        self.assertEqual(keys[:2], [("", ""), ("intro", "")])
        self.assertEqual(keys[-1], ("other", ""))

    def test_conflict_unresolved_keeps_ours(self) -> None:
        ours = edit(BASE, "Careful with numbers.", "Precise.")
        theirs = edit(BASE, "Careful with numbers.", "Imaginative.")
        result = merge(BASE, ours, theirs)
        self.assertEqual(result.text, ours)
        self.assertEqual(result.unresolved, [("profile", "")])
        self.assertEqual(result.changes[0].status, CONFLICT)

    def test_conflict_resolutions(self) -> None:
        ours = edit(BASE, "Careful with numbers.", "Precise.")
        theirs = edit(BASE, "Careful with numbers.", "Imaginative.")
        key = ("profile", "")
        self.assertEqual(merge(BASE, ours, theirs, resolutions={key: KEEP_OURS}).text, ours)
        self.assertEqual(merge(BASE, ours, theirs, resolutions={key: TAKE_THEIRS}).text, theirs)
        custom = merge(BASE, ours, theirs, resolutions={key: "# Profile\nPrecise and imaginative.\n"})
        self.assertIn("Precise and imaginative.", custom.text)
        self.assertEqual(custom.applied, [key])
        self.assertNotIn("# Profile", merge(BASE, ours, theirs, resolutions={key: None}).text)

    def test_removed_on_ours_changed_on_theirs_is_a_conflict(self) -> None:
        ours = edit(BASE, "# Skills\nLanguages: Maths\n", "")
        theirs = edit(BASE, "Languages: Maths", "Languages: Maths, Poetry")
        result = merge(BASE, ours.rstrip("\n") + "\n", theirs)
        self.assertEqual(result.unresolved, [("skills", "")])
        restored = merge(BASE, ours, theirs, resolutions={("skills", ""): TAKE_THEIRS})
        self.assertTrue(restored.text.endswith("# Skills\nLanguages: Maths, Poetry\n"))

    def test_merged_text_still_parses_and_lints(self) -> None:
        theirs = edit(BASE, "- Wrote the first program.", "- Wrote the first program.\n- Noted the engine could do more than numbers.")
        result = merge(BASE, BASE, theirs)
        errors = [i for i in lint_cv_source(parse_cv_source(result.text)) if i["level"] == "error"]
        self.assertEqual(errors, [])
        self.assertEqual(len(parse_cv_source(result.text)["sections"]["roles"]["entries"][0]["bullets"]), 2)


class DiffTests(unittest.TestCase):
    def test_change_diff_shows_lines(self) -> None:
        theirs = edit(BASE, "Languages: Maths", "Languages: Maths, Poetry")
        diff = compare(BASE, BASE, theirs)[0].diff
        self.assertIn("-Languages: Maths", diff)
        self.assertIn("+Languages: Maths, Poetry", diff)

    def test_unit_diff_for_addition_and_removal(self) -> None:
        self.assertIn("+# Other", unit_diff(None, "# Other\n- Chess."))
        self.assertIn("-# Other", unit_diff("# Other", None))


if __name__ == "__main__":
    unittest.main()
