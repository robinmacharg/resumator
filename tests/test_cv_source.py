import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cv_source import lint_cv_source, main, parse_cv_source, parse_dates, prompt_text

MINIMAL = """# Candidate
Name: Ada Lovelace
Headline: Engineer
Phone: 01234
Email: ada@example.com

# Roles

## Analyst | Engine Co
Dates: Jan 2020 - Present
Keywords: Maths

- Wrote the first program.
"""


def lint(text: str) -> list[dict]:
    return lint_cv_source(parse_cv_source(text))


def messages(text: str, level: str) -> list[str]:
    return [item["message"] for item in lint(text) if item["level"] == level]


class ParseDatesTests(unittest.TestCase):
    def test_accepts_supported_forms(self) -> None:
        self.assertEqual(parse_dates("May 2023 - Sep 2023"), {"start": "2023-05", "end": "2023-09"})
        self.assertEqual(parse_dates("Nov 2023 – Present"), {"start": "2023-11", "end": "present"})
        self.assertEqual(parse_dates("2016"), {"start": "2016", "end": None})
        self.assertEqual(parse_dates("2014 - Jun 2017"), {"start": "2014", "end": "2017-06"})

    def test_rejects_other_forms(self) -> None:
        for value in ("September 2023", "Sept 2023", "May 2023-Sep 2023", "Present", "Sep 2023 - May 2023", "TODO"):
            with self.subTest(value=value):
                self.assertIsNone(parse_dates(value))


class ParseCvSourceTests(unittest.TestCase):
    def test_parses_sections_entries_fields_and_bullets(self) -> None:
        doc = parse_cv_source(MINIMAL)

        candidate = doc["sections"]["candidate"]["fields"]
        self.assertEqual(candidate["name"], ["Ada Lovelace"])
        role = doc["sections"]["roles"]["entries"][0]
        self.assertEqual((role["title"], role["subtitle"]), ("Analyst", "Engine Co"))
        self.assertEqual(role["fields"]["dates"], ["Jan 2020 - Present"])
        self.assertEqual(role["bullets"][0]["text"], "Wrote the first program.")
        self.assertEqual(lint_cv_source(doc), [])

    def test_repeated_fields_keep_every_value_and_keys_are_case_insensitive(self) -> None:
        doc = parse_cv_source(MINIMAL.replace("Phone: 01234", "Phone: 01234\nPHONE: 05678"))

        self.assertEqual(doc["sections"]["candidate"]["fields"]["phone"], ["01234", "05678"])

    def test_bullet_continuation_survives_comment_only_line(self) -> None:
        text = MINIMAL.replace(
            "- Wrote the first program.",
            "- Wrote the first\n  <!-- note -->\n  program.",
        )

        bullets = parse_cv_source(text)["sections"]["roles"]["entries"][0]["bullets"]

        self.assertEqual([bullet["text"] for bullet in bullets], ["Wrote the first program."])

    def test_comments_are_removed_and_line_numbers_kept(self) -> None:
        text = "<!--\nheader\n-->\n" + MINIMAL.replace("Dates: Jan 2020 - Present", "Dates: Janu 2020 <!-- x -->")
        doc = parse_cv_source(text)

        self.assertNotIn("<!--", doc["prompt_text"])
        self.assertNotIn("header", doc["prompt_text"])
        self.assertTrue(doc["prompt_text"].startswith("# Candidate"))
        bad_dates = [item for item in lint_cv_source(doc) if "bad Dates" in item["message"]]
        self.assertEqual(bad_dates[0]["line"], 12)
        self.assertIn("'Janu 2020'", bad_dates[0]["message"])

    def test_elision_is_kept_in_prompt_and_collected_by_scope(self) -> None:
        text = MINIMAL + (
            "\n## ~~Spy | Secret Co~~\nDates: 2010 - 2011\n~~Keywords: Ciphers~~\n\n"
            "- ~~Held back.~~\n- Delivered for ~~three~~ clients.\n"
        )
        doc = parse_cv_source(text)

        scopes = {(item["scope"], item["text"]) for item in doc["elided"]}
        self.assertEqual(
            scopes,
            {
                ("entry", "Spy | Secret Co"),
                ("field", "Keywords: Ciphers"),
                ("bullet", "Held back."),
                ("phrase", "three"),
            },
        )
        spy = doc["sections"]["roles"]["entries"][1]
        self.assertTrue(spy["elided"])
        self.assertEqual(spy["fields"]["keywords"], ["Ciphers"])
        self.assertEqual(spy["elided_fields"], ["keywords"])
        self.assertIn("~~three~~", doc["prompt_text"])

    def test_directives_have_defaults_and_overrides(self) -> None:
        self.assertEqual(parse_cv_source(MINIMAL)["directives"], {"omit": [], "contact_links": True})

        doc = parse_cv_source(MINIMAL + "\n# Directives\nOmit: Keywords, location\nContact links: no\n")

        self.assertEqual(doc["directives"], {"omit": ["keywords", "location"], "contact_links": False})

    def test_profile_lines_with_colons_stay_prose(self) -> None:
        doc = parse_cv_source(MINIMAL + "\n# Profile\nNote: I like engines.\n")

        self.assertEqual(doc["sections"]["profile"]["prose"], ["Note: I like engines."])
        self.assertEqual(doc["sections"]["profile"]["fields"], {})

    def test_url_lines_are_not_fields(self) -> None:
        doc = parse_cv_source(MINIMAL + "\n# Other\nhttps://example.com\n")

        self.assertEqual(doc["sections"]["other"]["fields"], {})
        self.assertEqual(doc["sections"]["other"]["prose"], ["https://example.com"])


class LintCvSourceTests(unittest.TestCase):
    def test_missing_sections_and_required_fields_are_errors(self) -> None:
        errors = messages("# Candidate\nName: Ada\n", "error")

        self.assertIn("missing required section '# Roles'", errors)
        self.assertIn("# Candidate: missing required field 'Email'", errors)
        self.assertIn("# Candidate: missing required field 'Headline'", errors)

    def test_role_without_dates_is_an_error(self) -> None:
        errors = messages(MINIMAL.replace("Dates: Jan 2020 - Present\n", ""), "error")

        self.assertEqual(errors, ["'Analyst | Engine Co': missing required field 'Dates'"])

    def test_structural_mistakes_are_warnings(self) -> None:
        text = MINIMAL.replace("- Wrote the first program.", "- Wrote it.\nSummary: late field\nKeywords: twice")
        text = text.replace("## Analyst | Engine Co", "## Analyst | Engine Co\nColour: blue\nType: gig")
        text += "\n## TODO\nDates: 2018\n\n# Skills\nLanguages: Python\nLanguages: Ada\n- stray bullet\n"

        warnings = messages(text, "warning")

        for expected in (
            "'Analyst | Engine Co': unknown field 'colour'",
            "'Analyst | Engine Co': Type 'gig' is not one of permanent, contract, freelance, voluntary",
            "field 'Summary' after bullets; fields go first",
            "'Analyst | Engine Co': field 'keywords' given 2 times; only the first is used",
            "role 'TODO' has no '| Company' in its heading",
            "TODO left in: ## TODO",
            "# Skills: field 'languages' given 2 times; only the first is used",
            "bullets are not used in '# Skills'",
        ):
            self.assertIn(expected, warnings)

    def test_role_order_and_overlap(self) -> None:
        text = MINIMAL.replace("Jan 2020 - Present", "Jan 2015 - Present") + (
            "\n## Clerk | Office\nDates: Mar 2016 - 2017\n\n## Intern | Lab\nDates: Jun 2010 - Dec 2010\n"
        )

        issues = lint(text)

        self.assertIn(
            "role 'Clerk | Office' starts after the role above it; list newest first",
            [item["message"] for item in issues if item["level"] == "warning"],
        )
        self.assertEqual(
            [item["message"] for item in issues if item["level"] == "info"],
            ["role 'Analyst | Engine Co' overlaps 'Clerk | Office'"],
        )

    def test_unknown_section_is_info_and_bad_directive_is_error(self) -> None:
        issues = lint(MINIMAL + "\n# Hobbies\n- Chess\n\n# Directives\nContact links: maybe\nOmit: hobbies\n")
        found = {(item["level"], item["message"]) for item in issues}

        self.assertIn(("info", "unknown section '# Hobbies'; sent to the model as context"), found)
        self.assertIn(("error", "Contact links: 'maybe' should be yes or no"), found)
        self.assertIn(("warning", "Omit: 'hobbies' is not an entry field"), found)

    def test_unmatched_elision_marker_and_bad_links(self) -> None:
        text = MINIMAL.replace("- Wrote the first program.", "- Wrote ~~the first program.")
        text = text.replace("Keywords: Maths", "Link: https://example.com")
        text = text.replace("Email: ada@example.com", "Email: ada@example.com\nGitHub: github.com/ada")

        warnings = messages(text, "warning")

        self.assertIn("unmatched ~~ (elision marker)", warnings)
        self.assertIn("'Analyst | Engine Co': Link 'https://example.com' should be '<label> <url>'", warnings)
        self.assertIn("# Candidate: 'github' should be a full URL", warnings)

    def test_worked_example_has_no_errors_or_warnings(self) -> None:
        text = Path(__file__).resolve().parent.parent.joinpath("input", "CV.v2.md").read_text(encoding="utf-8")

        levels = {item["level"] for item in lint(text)}

        self.assertLessEqual(levels, {"info"})


class PromptTextTests(unittest.TestCase):
    def test_collapses_blank_runs_left_by_comments(self) -> None:
        self.assertEqual(prompt_text("# A\n\n<!-- x -->\n\n\nb\n"), "# A\n\nb\n")


class CliTests(unittest.TestCase):
    def run_cli(self, text: str, *flags: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "CV.md"
            path.write_text(text, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = main([str(path), *flags])
        return code, out.getvalue()

    def test_lint_exit_code_reflects_errors(self) -> None:
        self.assertEqual(self.run_cli(MINIMAL, "--lint"), (0, ""))

        code, output = self.run_cli("# Candidate\n", "--lint")

        self.assertEqual(code, 1)
        self.assertIn(":1: error: missing required section '# Roles'", output)

    def test_json_dumps_parsed_dict(self) -> None:
        code, output = self.run_cli(MINIMAL, "--json")

        self.assertEqual(code, 0)
        self.assertIn('"contact_links": true', output)


if __name__ == "__main__":
    unittest.main()
