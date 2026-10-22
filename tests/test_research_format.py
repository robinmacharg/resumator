import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import research_format
from research_format import format_markdown, render_research_pdf

ENV = {"CV_FONT_PRIORITY": "Helvetica"}


class FormatMarkdownTests(unittest.TestCase):
    def test_adds_heading_when_missing(self):
        self.assertEqual(format_markdown("Body text", "Notes"), "# Notes\n\nBody text")

    def test_keeps_existing_heading(self):
        self.assertEqual(format_markdown("# Acme\n\nBody"), "# Acme\n\nBody")

    def test_drops_rules_and_collapses_blank_lines(self):
        text = "# Acme\r\n\r\n\r\n\r\nOne   \n---\n\n\n\nTwo\n\n\n"
        self.assertEqual(format_markdown(text), "# Acme\n\n\nOne\n\n\nTwo")


class RenderResearchPdfTests(unittest.TestCase):
    def test_refuses_empty_markdown(self):
        with self.assertRaisesRegex(RuntimeError, "empty"):
            render_research_pdf("  \n", env=ENV)

    def test_compiles_formatted_markdown_in_a_temp_dir(self):
        seen = {}

        def fake_compile(markdown_file, output_pdf, font_name):
            seen["markdown"] = markdown_file.read_text(encoding="utf-8")
            seen["font"] = font_name
            output_pdf.write_bytes(b"%PDF-fake")

        with mock.patch.object(research_format, "compile_pdf", side_effect=fake_compile), \
                mock.patch.object(research_format, "choose_font", return_value="Helvetica"):
            data = render_research_pdf("Body", "Acme", env=ENV)
        self.assertEqual(data, b"%PDF-fake")
        self.assertEqual(seen, {"markdown": "# Acme\n\nBody\n", "font": "Helvetica"})

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_renders_real_pdf(self):
        data = render_research_pdf("## Overview\n\n- Point one\n- Point two\n", "Acme", env=ENV)
        self.assertTrue(data.startswith(b"%PDF"))


class FileRunTests(unittest.TestCase):
    def test_run_writes_formatted_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "research_output.md"
            source.write_text("Body\n---\n", encoding="utf-8")
            with mock.patch.object(research_format, "compile_pdf"), \
                    mock.patch.object(research_format, "choose_font", return_value="Helvetica"), \
                    redirect_stdout(io.StringIO()):
                code = research_format.run(source, root / "out.md", root / "out.pdf", "Notes", env=ENV)
            self.assertEqual(code, 0)
            self.assertEqual((root / "out.md").read_text(encoding="utf-8"), "# Notes\n\nBody\n")


if __name__ == "__main__":
    unittest.main()
