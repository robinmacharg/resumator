import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import generate_cv
from generate_cv import (
    build_prompt,
    build_run_facts,
    build_steering_section,
    count_pdf_pages,
    earlier_career_span,
    find_elision_leaks,
    record_run_metadata,
    selected_roles_cutoff,
    normalize_date_range,
    parse_and_validate_json_output,
    render_tagged_markdown,
    validate_and_normalize_payload,
)


def valid_payload() -> dict:
    return {
        "candidate": {
            "name": "Ada Lovelace",
            "phone": "+44 123",
            "email": "ada@example.com",
            "linkedin": "https://linkedin.com/in/ada",
            "github": None,
            "stackoverflow": "",
            "website": None,
            "location": "London",
            "subheader_lines": ["Portfolio: [ada.dev](https://ada.dev)"],
        },
        "metadata": {"company": "Engine Co"},
        "document": {
            "headline": "Analyst and Programmer",
            "professional_summary": [f"**Point {n}** evidence." for n in range(4)],
            "role_requirements": {
                "role_title": "Senior Analyst",
                "items": ["- **Maths:** Bernoulli numbers."] + [f"**Req {n}:** proof." for n in range(3)],
            },
            "education_credentials": ["Mathematics - private tutors"],
            "selected_key_roles": [
                {
                    "title": "Analyst",
                    "company": "Engine Co",
                    "date_range": "October 2021 – present",
                    "app_store_url": "https://apps.apple.com/x",
                    "keywords": ["Maths", "Notes"],
                    "bullets": ["* Wrote the first program.", "Translated Menabrea."],
                }
            ],
            "earlier_career": {
                "sectors": ["mathematics", "translation", "poetry"],
                "items": [
                    {
                        "role_title": "Translator",
                        "company": "Menabrea",
                        "technologies": ["French"],
                        "date_range": "Mar 2015 to SEPT 2018",
                    },
                    {
                        "role_title": "Student",
                        "company": "Tutors",
                        "technologies": [],
                        "date_range": "1996 - 2001",
                    },
                ],
            },
            "open_source_contributions": ["- Note G", "Difference Engine notes", "Bernoulli tables"],
            "technical_skills": [{"group": "Maths", "items": ["Algebra", "Calculus"]}],
        },
    }


class NormalizeDateRangeTests(unittest.TestCase):
    def test_rewrites_to_three_letter_months(self) -> None:
        self.assertEqual(normalize_date_range("October 2021 – present", "f"), "Oct 2021 - Present")
        self.assertEqual(normalize_date_range("Mar 2015 to SEPT 2018", "f"), "Mar 2015 - Sep 2018")
        self.assertEqual(normalize_date_range("1996-2001", "f"), "1996 - 2001")

    def test_single_point_is_kept(self) -> None:
        self.assertEqual(normalize_date_range("2016", "f"), "2016")
        self.assertEqual(normalize_date_range("May 2023 - may 2023", "f"), "May 2023")

    def test_rejects_bad_ranges(self) -> None:
        for value in ["Present", "Smarch 2019 - 2020", "Present - 2020", "Jan 2020 - Dec 2019", "", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_date_range(value, "f")

    def test_earlier_career_span_uses_widest_bounds(self) -> None:
        items = [{"date_range": "Mar 2015 - Sep 2018"}, {"date_range": "1996 - 2001"}]
        self.assertEqual(earlier_career_span(items), "1996 - 2018")
        items.append({"date_range": "2010 - Present"})
        self.assertEqual(earlier_career_span(items), "1996 - Present")


class ValidateAndNormalizePayloadTests(unittest.TestCase):
    def validate(self, payload: dict | None = None, **kwargs) -> dict:
        return validate_and_normalize_payload(payload or valid_payload(), **kwargs)

    def assert_invalid(self, mutate, message: str, **kwargs) -> None:
        payload = valid_payload()
        mutate(payload)
        with self.assertRaisesRegex(ValueError, message):
            self.validate(payload, **kwargs)

    def test_valid_payload_is_normalised(self) -> None:
        payload = self.validate()
        candidate = payload["candidate"]
        self.assertNotIn("location", candidate)
        self.assertIsNone(candidate["github"])
        self.assertIsNone(candidate["stackoverflow"])
        document = payload["document"]
        self.assertEqual(document["role_requirements"]["items"][0], "**Maths:** Bernoulli numbers.")
        role = document["selected_key_roles"][0]
        self.assertEqual(role["date_range"], "Oct 2021 - Present")
        self.assertEqual(role["bullets"], ["Wrote the first program.", "Translated Menabrea."])
        self.assertEqual(document["earlier_career"]["items"][0]["date_range"], "Mar 2015 - Sep 2018")
        self.assertEqual(document["open_source_contributions"][0], "Note G")

    def test_metadata_is_optional(self) -> None:
        payload = valid_payload()
        del payload["metadata"]
        self.assertEqual(self.validate(payload)["metadata"], {})

    def test_v1_only_keys_are_not_required(self) -> None:
        payload = valid_payload()
        self.assertNotIn("semantic_tags", payload)
        self.assertNotIn("skills_raw", payload)
        self.validate(payload)

    def test_required_fields(self) -> None:
        cases = [
            (lambda p: p.pop("document"), "Missing required top-level key: document"),
            (lambda p: p["candidate"].pop("email"), "candidate.email"),
            (lambda p: p["document"].pop("headline"), "document.headline"),
            (lambda p: p["document"]["role_requirements"].pop("role_title"), "role_title"),
            (lambda p: p["document"]["earlier_career"].pop("sectors"), "sectors"),
            (lambda p: p["document"]["selected_key_roles"][0].pop("company"), r"\[0\]\.company"),
        ]
        for mutate, message in cases:
            with self.subTest(message=message):
                self.assert_invalid(mutate, message)

    def test_list_lengths(self) -> None:
        cases = [
            (lambda p: p["document"]["professional_summary"].pop(), "professional_summary must include at least 4"),
            (lambda p: p["document"]["education_credentials"].extend(["b", "c", "d"]), "at most 3"),
            (lambda p: p["document"]["open_source_contributions"].extend(["d", "e"]), "at most 4"),
            (lambda p: p["document"]["selected_key_roles"][0]["bullets"].extend(["a"] * 4), "at most 5"),
            (lambda p: p["document"]["selected_key_roles"].extend(
                copy.deepcopy(p["document"]["selected_key_roles"]) * 5), "at most 5 roles"),
        ]
        for mutate, message in cases:
            with self.subTest(message=message):
                self.assert_invalid(mutate, message)

    def test_bold_lead_in_required(self) -> None:
        self.assert_invalid(
            lambda p: p["document"]["professional_summary"].__setitem__(0, "No bold."),
            r"professional_summary\[0\] must open with a \*\*bold phrase\*\*",
        )
        self.assert_invalid(
            lambda p: p["document"]["role_requirements"]["items"].__setitem__(1, "- plain"),
            r"items\[1\] must open",
        )

    def test_urls_must_be_http(self) -> None:
        self.assert_invalid(
            lambda p: p["document"]["selected_key_roles"][0].__setitem__("app_store_url", "apps.apple.com/x"),
            "app_store_url must be an http",
        )

    def test_role_cutoff_warns_and_keeps_the_role(self) -> None:
        warnings: list[str] = []
        self.validate(role_cutoff=(2016, 10), warnings=warnings)
        self.assertEqual(warnings, [])
        payload = self.validate(role_cutoff=(2021, 11), warnings=warnings)
        self.assertEqual(len(payload["document"]["selected_key_roles"]), 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("(Analyst | Engine Co) starts Oct 2021, before the selected-roles cutoff Nov 2021", warnings[0])

    def test_role_cutoff_gives_year_only_starts_the_benefit_of_the_doubt(self) -> None:
        payload = valid_payload()
        payload["document"]["selected_key_roles"][0]["date_range"] = "2016 - 2018"
        warnings: list[str] = []
        self.validate(payload, role_cutoff=(2016, 10), warnings=warnings)
        self.assertEqual(warnings, [])

    def test_list_caps_warn_and_keep_the_output(self) -> None:
        payload = valid_payload()
        document = payload["document"]
        document["earlier_career"]["items"] *= 5
        document["technical_skills"] *= 6
        warnings: list[str] = []
        result = self.validate(payload, warnings=warnings)
        self.assertEqual(len(result["document"]["earlier_career"]["items"]), 10)
        self.assertEqual(
            warnings,
            [
                "document.earlier_career has 10 items; the limit is 8.",
                "document.technical_skills has 6 groups; the limit is 5.",
            ],
        )

    def test_parse_and_validate_json_output_extracts_fenced_json(self) -> None:
        raw = "Here you go:\n```json\n" + json.dumps(valid_payload()) + "\n```"
        payload = parse_and_validate_json_output(raw, role_cutoff=(2016, 1))
        self.assertEqual(payload["candidate"]["name"], "Ada Lovelace")


class RenderTaggedMarkdownTests(unittest.TestCase):
    def render(self, **kwargs) -> list[str]:
        return render_tagged_markdown(validate_and_normalize_payload(valid_payload()), **kwargs).splitlines()

    def test_front_matter_holds_candidate_and_metadata_only(self) -> None:
        lines = self.render()
        front_matter = lines[: lines.index("---", 1) + 1]
        self.assertIn("candidate:", front_matter)
        self.assertIn("metadata:", front_matter)
        self.assertFalse(any(line.startswith(("semantic_tags", "skills_raw")) for line in front_matter))

    def test_subheader(self) -> None:
        lines = self.render()
        self.assertIn("[candidate_title] Analyst and Programmer", lines)
        self.assertIn("[candidate_contact] +44 123 - [ada@example.com](mailto:ada@example.com)", lines)
        self.assertIn("[candidate_contact] [LinkedIn](https://linkedin.com/in/ada)", lines)
        self.assertIn("[candidate_subheader] Portfolio: [ada.dev](https://ada.dev)", lines)

    def test_contact_links_directive(self) -> None:
        lines = self.render(directives={"contact_links": False})
        self.assertNotIn("[candidate_contact] [LinkedIn](https://linkedin.com/in/ada)", lines)

    def test_fixed_requirements_heading(self) -> None:
        lines = self.render()
        self.assertIn("[role_requirements_heading] ### Targeted Requirements Match for Senior Analyst", lines)
        self.assertIn("[role_requirements_item] - **Maths:** Bernoulli numbers.", lines)

    def test_role_block(self) -> None:
        lines = self.render()
        start = lines.index("[role_heading] ## Analyst | Engine Co")
        self.assertEqual(
            lines[start + 1 : start + 5],
            [
                "[date_range] Oct 2021 - Present ([AppStore](https://apps.apple.com/x))",
                "[keywords] Keywords: [Maths, Notes]",
                "[role_bullet] * Wrote the first program.",
                "[role_bullet] * Translated Menabrea.",
            ],
        )

    def test_omit_keywords_directive(self) -> None:
        lines = self.render(directives={"omit": ["Keywords"]})
        self.assertFalse(any(line.startswith("[keywords]") for line in lines))

    def test_earlier_career(self) -> None:
        lines = self.render()
        self.assertIn(
            "[earlier_intro] **1996 - 2018** Positions across mathematics, translation, and poetry.",
            lines,
        )
        self.assertIn("[earlier_role] * **Translator** | _Menabrea_ (French) - Mar 2015 - Sep 2018", lines)
        self.assertIn("[earlier_role] * **Student** | _Tutors_ - 1996 - 2001", lines)

    def test_projects_and_skills(self) -> None:
        lines = self.render()
        self.assertIn("[project_item] * Note G", lines)
        self.assertIn("[skills_group] **Maths** - Algebra, Calculus", lines)


class RunFactsTests(unittest.TestCase):
    def test_cutoff_is_ten_years_to_the_month(self) -> None:
        self.assertEqual(selected_roles_cutoff(date(2026, 10, 21)), (2016, 10))

    def test_run_facts_block(self) -> None:
        facts = build_run_facts(date(2026, 10, 21), (2016, 10), {"omit": ["keywords"], "contact_links": True})
        self.assertEqual(
            facts.splitlines(),
            [
                "=== RUN FACTS ===",
                "Today: Oct 2026",
                "Selected-roles cutoff: Oct 2016",
                "Directives: Omit: keywords; Contact links: yes",
            ],
        )

    def test_run_facts_weightings(self) -> None:
        facts = build_run_facts(
            date(2026, 1, 1),
            (2016, 1),
            {"omit": [], "contact_links": True, "emphasise": ["AI tooling", "LLMs"], "downplay": ["Android"]},
        )
        self.assertIn("Directives: Contact links: yes; Emphasise: AI tooling, LLMs; Downplay: Android", facts)

    def test_run_facts_without_omit(self) -> None:
        facts = build_run_facts(date(2026, 1, 1), (2016, 1), {"omit": [], "contact_links": False})
        self.assertIn("Directives: Contact links: no", facts)


class BuildPromptTests(unittest.TestCase):
    def test_sections_follow_inputs_in_order(self) -> None:
        prompt = build_prompt(
            "Prompt {not a placeholder}",
            "cv",
            "spec",
            run_facts="=== RUN FACTS ===\nToday: Oct 2026",
            steering=build_steering_section("  multi-domain skills\n"),
        )
        order = [prompt.index(marker) for marker in
                 ("=== MASTER CV ===", "=== JOB SPECIFICATION ===", "=== RUN FACTS ===", "=== CANDIDATE STEERING ===")]
        self.assertEqual(order, sorted(order))
        self.assertTrue(prompt.endswith('Steering: "multi-domain skills"'))

    def test_empty_steering_adds_nothing(self) -> None:
        self.assertEqual(build_steering_section(" \n "), "")
        self.assertNotIn("STEERING", build_prompt("Prompt", "cv", "spec", steering=""))


class ElisionLeakTests(unittest.TestCase):
    MARKDOWN = "\n".join([
        "---",
        "metadata:",
        '  note: "Secret Project | Acme"',
        "---",
        "[role_heading] ## Engineer | Acme",
        "[role_bullet] * Led the **migration** to three regions.",
        "[earlier_role] * **Secret Project** | _Acme_ (C) - 2001 - 2002",
    ])

    def leaks(self, *items: tuple[str, str]) -> list[str]:
        return find_elision_leaks([{"text": text, "line": 7, "scope": scope} for scope, text in items], self.MARKDOWN)

    def test_entry_heading_matches_through_markup(self) -> None:
        self.assertEqual(len(self.leaks(("entry", "Secret Project | Acme"))), 1)

    def test_bullet_and_field_value(self) -> None:
        self.assertEqual(len(self.leaks(("bullet", "Led the migration to three regions."))), 1)
        self.assertEqual(len(self.leaks(("field", "Keywords: C"))), 1)
        self.assertEqual(self.leaks(("bullet", "Led a different migration")), [])

    def test_short_phrases_are_skipped(self) -> None:
        self.assertEqual(self.leaks(("phrase", "three")), [])
        self.assertEqual(len(self.leaks(("phrase", "to three regions"))), 1)

    def test_front_matter_is_ignored(self) -> None:
        markdown = self.MARKDOWN.replace("[earlier_role] * **Secret Project** | _Acme_ (C) - 2001 - 2002", "")
        self.assertEqual(find_elision_leaks([{"text": "Secret Project | Acme", "line": 1, "scope": "entry"}], markdown), [])


class PdfPageCountTests(unittest.TestCase):
    def count(self, data: bytes) -> int | None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.pdf"
            path.write_bytes(data)
            return count_pdf_pages(path)

    def test_reads_root_page_tree(self) -> None:
        data = (
            b"%PDF-1.7\n1 0 obj\n<</Type/Pages/Count 3/Kids[2 0 R 3 0 R]>>\nendobj\n"
            b"2 0 obj\n<</Type /Pages /Parent 1 0 R /Count 2 /Kids[4 0 R 5 0 R]>>\nendobj\n"
            b"4 0 obj\n<</Type/Page/Parent 2 0 R>>\nendobj\n"
        )
        self.assertEqual(self.count(data), 3)

    def test_unreadable_tree(self) -> None:
        self.assertIsNone(self.count(b"%PDF-1.7\n<</Type/ObjStm>>"))
        self.assertIsNone(count_pdf_pages(Path("/nonexistent/cv.pdf")))


class RecordRunMetadataTests(unittest.TestCase):
    def test_adds_run_facts_to_model_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tailored.model.json"
            with mock.patch.object(generate_cv, "RAW_MODEL_JSON_FILE", path):
                record_run_metadata('{"metadata": {"company": "X"}, "document": {}}', "lead", 2, ["w1"])
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["metadata"], {"company": "X", "steering": "lead", "page_count": 2, "warnings": ["w1"]}
        )

    def test_unparseable_json_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tailored.model.json"
            with mock.patch.object(generate_cv, "RAW_MODEL_JSON_FILE", path):
                record_run_metadata("not json", "", None, [])
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
