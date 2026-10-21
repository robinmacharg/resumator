import io
import os
import re
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import cv_convert
from cv_convert import (
    DEFAULT_TYPST_THEME,
    THEMES_DIR,
    apply_semantic_tag_formatting,
    available_themes,
    build_docx_reference,
    convert_markdown_outputs,
    count_pdf_pages,
    export_markdown,
    process_docx_reference,
    render_cv,
    typst_theme_files,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_MARKDOWN = REPO_ROOT / "output" / "tailored.md"

TAGGED = """---
candidate:
  name: "Ada Lovelace"
---

[candidate_name] Ada Lovelace
[candidate_title] Analyst
[candidate_contact] [Call](tel:%2B44123) - [Email](mailto:ada@example.com)
[candidate_contact] [GitHub](https://github.com/ada)
[candidate_subheader] Portfolio: ada.dev

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
[role_bullet] * Annotated the Sketch.

[section_heading] # Earlier Career Highlights

[earlier_intro] **1830 - 1840** Positions across mathematics and translation.
[earlier_role] * **Translator** | _Menabrea_ (French) - 1840 - 1843

[skills_group] **Maths** - Algebra, Calculus

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

    def test_consecutive_summary_points_become_one_paragraph(self) -> None:
        text = apply_semantic_tag_formatting(
            "[summary_paragraph] **Pioneer** of programming.\n"
            "[summary_paragraph] **Translator** of *Menabrea*.\n"
            "[section_heading] # Education\n"
            "[summary_paragraph] **Later** point.\n"
        )
        lines = text.splitlines()
        blocks = [lines[i + 1] for i, line in enumerate(lines) if line == styled("summary-item")]
        self.assertEqual(
            blocks,
            ["**Pioneer** of programming. **Translator** of Menabrea.", "**Later** point."],
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

    def test_v2_tags(self) -> None:
        self.assertEqual(self.block_after("candidate-subheader"), "Portfolio: ada.dev")
        self.assertEqual(
            self.block_after("earlier-intro"),
            "**1830 - 1840** Positions across mathematics and translation.",
        )
        self.assertIn("- Annotated the Sketch.", self.lines)
        self.assertIn(
            '- [Translator]{custom-style="earlier-title"} | '
            '[Menabrea]{custom-style="earlier-company"} (French) - 1840 - 1843',
            self.lines,
        )
        self.assertIn('[Maths]{custom-style="skills-group"} - Algebra, Calculus', self.lines)

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

    def test_available_themes_lists_default_then_presets(self) -> None:
        presets = sorted(path.stem for path in THEMES_DIR.glob("*.typ") if path != DEFAULT_TYPST_THEME)
        self.assertEqual(available_themes(), ["default", *presets])
        self.assertIn("compact", available_themes())

    def test_summary_and_requirements_are_not_justified(self) -> None:
        theme = DEFAULT_TYPST_THEME.read_text(encoding="utf-8")
        self.assertIn("summary-justify: false", theme)
        self.assertEqual(theme.count("set par(justify: t.summary-justify)"), 2)

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


class CountPdfPagesTests(unittest.TestCase):
    def test_reads_root_page_tree(self) -> None:
        data = (
            b"%PDF-1.7\n1 0 obj\n<</Type/Pages/Count 3/Kids[2 0 R 3 0 R]>>\nendobj\n"
            b"2 0 obj\n<</Type /Pages /Parent 1 0 R /Count 2 /Kids[4 0 R 5 0 R]>>\nendobj\n"
            b"4 0 obj\n<</Type/Page/Parent 2 0 R>>\nendobj\n"
        )
        self.assertEqual(count_pdf_pages(data), 3)

    def test_unreadable_tree(self) -> None:
        self.assertIsNone(count_pdf_pages(b"%PDF-1.7\n<</Type/ObjStm>>"))
        self.assertIsNone(count_pdf_pages(b""))


class ExportMarkdownTests(unittest.TestCase):
    def test_strips_front_matter_after_tagging(self) -> None:
        text, stripped = export_markdown(TAGGED)
        self.assertTrue(stripped)
        self.assertTrue(text.startswith(styled("candidate-name")))
        self.assertTrue(text.endswith("\n"))

    def test_without_front_matter(self) -> None:
        text, stripped = export_markdown("[candidate_name] Ada\n")
        self.assertFalse(stripped)
        self.assertEqual(text, apply_semantic_tag_formatting("[candidate_name] Ada\n") + "\n")

    def test_unknown_format_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_cv(TAGGED, output_format="html")


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "pandoc and typst not installed")
class RenderCvTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(cv_convert, "choose_font", lambda fonts: fonts[0])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cwd = tempfile.TemporaryDirectory()
        self.addCleanup(self.cwd.cleanup)
        previous = os.getcwd()
        os.chdir(self.cwd.name)
        self.addCleanup(os.chdir, previous)

    def test_pdf_bytes_without_files(self) -> None:
        pdf = render_cv(TAGGED, "pdf", theme="compact")
        self.assertIsNotNone(pdf)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(count_pdf_pages(pdf), 1)
        self.assertEqual(os.listdir(self.cwd.name), [])

    def test_docx_bytes_without_files(self) -> None:
        docx = render_cv(TAGGED, "docx")
        self.assertIsNotNone(docx)
        document = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode("utf-8")
        self.assertIn('w:pStyle w:val="candidate-name"', document)
        self.assertEqual(os.listdir(self.cwd.name), [])

    def test_reference_docx_is_built_once_in_a_private_folder(self) -> None:
        first = process_docx_reference()
        self.assertEqual(process_docx_reference(), first)
        self.assertTrue(first.is_file())
        self.assertNotEqual(first.parent.resolve(), REPO_ROOT / "output")

    def test_theme_defaults_to_cv_theme_env(self) -> None:
        with mock.patch.dict(os.environ, {"CV_THEME": "compact"}), mock.patch.object(
            cv_convert, "render_pdf_bytes", return_value=b"%PDF"
        ) as render:
            render_cv(TAGGED)
        self.assertEqual(render.call_args.args[2], "compact")


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "pandoc and typst not installed")
@unittest.skipUnless(BASELINE_MARKDOWN.is_file(), "no local output/tailored.md baseline")
class RenderCvMatchesFileRouteTests(unittest.TestCase):
    """The in-memory render matches the file route on the user's real tailored.md (read-only, not committed)."""

    def test_same_pages_and_docx_body_as_file_route(self) -> None:
        markdown_text = BASELINE_MARKDOWN.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "tailored.md"
            source.write_text(markdown_text, encoding="utf-8")
            for theme in cv_convert.available_themes():
                with self.subTest(theme=theme):
                    convert_markdown_outputs(source, root / "out.pdf", root / "out.docx", theme=theme)
                    file_pdf = (root / "out.pdf").read_bytes()
                    memory_pdf = render_cv(markdown_text, "pdf", theme=theme)
                    self.assertEqual(count_pdf_pages(memory_pdf), count_pdf_pages(file_pdf))
            file_document = zipfile.ZipFile(root / "out.docx").read("word/document.xml")
        memory_document = zipfile.ZipFile(io.BytesIO(render_cv(markdown_text, "docx"))).read("word/document.xml")
        self.assertEqual(memory_document, file_document)


if __name__ == "__main__":
    unittest.main()
