import io
import re
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

import cv_convert
from cv_convert import (
    DEFAULT_TYPST_THEME,
    THEMES_DIR,
    apply_semantic_tag_formatting,
    build_docx_reference,
    convert_markdown_outputs,
    typst_theme_files,
)

TAGGED = """---
candidate:
  name: "Ada Lovelace"
---

[candidate_name] Ada Lovelace
[candidate_title] Analyst
[candidate_contact] [Call](tel:%2B44123) - [Email](mailto:ada@example.com)
[candidate_contact] [GitHub](https://github.com/ada)

[section_heading] # Professional Summary

[summary_paragraph] **Pioneer** of *programming* on the Analytical Engine.

[role_requirements_heading] ### Maths Alignment
[role_requirements_item] - **Maths:** Bernoulli numbers.
[role_requirements_item] - **Notes:** Note G.

[section_heading] # Education, Certifications & Credentials

[education_item] * Mathematics — Private tutors

[section_heading] # Selected Key Roles

[role_heading] ## Analyst | Engine Co
[date_range] **Dates:** Jan 1842 - Present ([AppStore](https://apps.apple.com/x))
[keywords] **Keywords:** `[Maths, Notes]`
[bullet_primary] * Wrote the first program.
[bullet_secondary] * Translated Menabrea.

**Untagged** line stays as is.
"""


def styled(style: str) -> str:
    return f'::: {{custom-style="{style}"}}'


class ApplySemanticTagFormattingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = apply_semantic_tag_formatting(TAGGED)
        self.lines = self.text.splitlines()

    def block_after(self, style: str, occurrence: int = 0) -> str:
        indexes = [i for i, line in enumerate(self.lines) if line == styled(style)]
        return self.lines[indexes[occurrence] + 1]

    def test_emits_no_raw_typst(self) -> None:
        self.assertNotIn("{=typst}", self.text)
        self.assertNotIn("#set", self.text)
        self.assertNotIn("#text", self.text)

    def test_tags_become_styled_divs(self) -> None:
        self.assertEqual(self.block_after("candidate-name"), "Ada Lovelace")
        self.assertEqual(self.block_after("candidate-title"), "Analyst")
        self.assertEqual(self.block_after("section-heading"), "Professional Summary")
        self.assertEqual(self.block_after("role-heading"), "Analyst | Engine Co")
        self.assertEqual(self.block_after("requirements-heading"), "Maths Alignment")

    def test_contact_unwraps_phone_and_shows_email(self) -> None:
        self.assertEqual(
            self.block_after("candidate-contact"),
            "+44123 - [ada@example.com](mailto:ada@example.com)",
        )
        self.assertEqual(self.block_after("candidate-contact", 1), "[GitHub](https://github.com/ada)")

    def test_summary_keeps_bold_and_drops_italics(self) -> None:
        self.assertEqual(
            self.block_after("summary-item"),
            "**Pioneer** of programming on the Analytical Engine.",
        )

    def test_requirements_items_become_one_styled_list(self) -> None:
        start = self.lines.index(styled("requirements-list"))
        self.assertEqual(
            self.lines[start + 1 : start + 4],
            ["- **Maths:** Bernoulli numbers.", "- **Notes:** Note G.", ":::"],
        )
        self.assertEqual(self.text.count(styled("requirements-list")), 1)

    def test_date_range_drops_label(self) -> None:
        self.assertEqual(
            self.block_after("date-range"),
            "Jan 1842 - Present ([AppStore](https://apps.apple.com/x))",
        )

    def test_keywords_are_plain_text(self) -> None:
        self.assertEqual(self.block_after("keywords"), "Keywords: [Maths, Notes]")

    def test_education_title_is_a_styled_span(self) -> None:
        self.assertIn('- [Mathematics]{custom-style="education-title"} — Private tutors', self.lines)

    def test_bullets_stay_plain_list_items(self) -> None:
        self.assertIn("- Wrote the first program.", self.lines)
        self.assertIn("- Translated Menabrea.", self.lines)

    def test_untagged_lines_pass_through(self) -> None:
        self.assertIn("**Untagged** line stays as is.", self.lines)

    def test_requirements_list_flushed_at_end_of_text(self) -> None:
        text = apply_semantic_tag_formatting("[role_requirements_item] - Last item")
        self.assertEqual(text.splitlines()[:3], [styled("requirements-list"), "- Last item", ":::"])


class ThemeFilesTests(unittest.TestCase):
    def test_default_theme_only(self) -> None:
        self.assertEqual(typst_theme_files(None), [DEFAULT_TYPST_THEME])
        self.assertEqual(typst_theme_files("default"), [DEFAULT_TYPST_THEME])

    def test_preset_layers_on_default(self) -> None:
        self.assertEqual(typst_theme_files("compact"), [DEFAULT_TYPST_THEME, THEMES_DIR / "compact.typ"])

    def test_unknown_preset_warns_and_uses_default(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            files = typst_theme_files("missing")
        self.assertEqual(files, [DEFAULT_TYPST_THEME])
        self.assertIn("Unknown theme preset 'missing'", stderr.getvalue())

    def test_every_emitted_style_has_a_typst_look(self) -> None:
        theme = DEFAULT_TYPST_THEME.read_text(encoding="utf-8")
        emitted = set(re.findall(r'custom-style="([^"]+)"', apply_semantic_tag_formatting(TAGGED)))
        missing = sorted(name for name in emitted if f"{name}:" not in theme)
        self.assertEqual(missing, [])


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
class DocxReferenceTests(unittest.TestCase):
    def test_merges_theme_styles_into_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reference = Path(tmp) / "reference.docx"
            self.assertTrue(build_docx_reference(reference))
            styles = zipfile.ZipFile(reference).read("word/styles.xml").decode("utf-8")
        self.assertIn('w:styleId="candidate-name"', styles)
        self.assertIn('w:styleId="Heading1"', styles)
        self.assertNotIn("<!--", styles)


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "pandoc and typst not installed")
class ConvertMarkdownOutputsTests(unittest.TestCase):
    def test_renders_pdf_and_docx_from_one_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "tailored.md"
            source.write_text(TAGGED, encoding="utf-8")
            original_choose_font = cv_convert.choose_font
            cv_convert.choose_font = lambda fonts: fonts[0]
            try:
                result = convert_markdown_outputs(
                    markdown_path=source,
                    output_pdf=root / "out.pdf",
                    output_docx=root / "out.docx",
                    theme="compact",
                )
            finally:
                cv_convert.choose_font = original_choose_font

            self.assertTrue(result.pdf_ok)
            self.assertTrue(result.docx_ok)
            self.assertTrue(result.used_sanitized_markdown)
            self.assertTrue((root / "out.pdf").read_bytes().startswith(b"%PDF"))
            self.assertFalse((root / "tailored.docx.export.md").exists())
            document = zipfile.ZipFile(root / "out.docx").read("word/document.xml").decode("utf-8")
            self.assertIn('w:pStyle w:val="candidate-name"', document)


if __name__ == "__main__":
    unittest.main()
