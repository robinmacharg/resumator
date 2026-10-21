import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cv_web import server, server_run_helpers
from cv_web.server_request_parsing import parse_selected_theme, parse_steering
from cv_web.server_state_helpers import read_output_steering


class ServerValidationHelpersTests(unittest.TestCase):
    def test_parse_company_name_trims_and_requires_value(self) -> None:
        self.assertEqual(server.parse_company_name({"companyName": "  Acme Corp  "}), "Acme Corp")

        with self.assertRaisesRegex(ValueError, "companyName is required"):
            server.parse_company_name({"companyName": "   "})

    def test_parse_url_list_validates_shape_and_items(self) -> None:
        urls = server.parse_url_list({"urls": [" https://one.example ", "", "https://two.example"]})
        self.assertEqual(urls, ["https://one.example", "https://two.example"])

        with self.assertRaisesRegex(ValueError, "urls must be a list of strings"):
            server.parse_url_list({"urls": "not-a-list"})

        with self.assertRaisesRegex(ValueError, "urls\[1\] must be a string"):
            server.parse_url_list({"urls": ["https://one.example", 42]})

    def test_parse_auto_format_pdf_defaults_and_rejects_non_bool(self) -> None:
        self.assertTrue(server.parse_auto_format_pdf({}))
        self.assertFalse(server.parse_auto_format_pdf({"autoFormatPdf": False}))

        with self.assertRaisesRegex(ValueError, "autoFormatPdf must be a boolean"):
            server.parse_auto_format_pdf({"autoFormatPdf": "yes"})

    def test_parse_research_run_request_parses_and_normalizes(self) -> None:
        payload = {
            "selectedProvider": "gemini",
            "selectedModel": "",
            "companyName": "  Example Inc  ",
            "urls": [" https://a.example ", "", "https://b.example"],
            "dryRun": 1,
            "autoFormatPdf": True,
        }

        req = server.parse_research_run_request(payload)

        self.assertEqual(req.company_name, "Example Inc")
        self.assertEqual(req.urls, ["https://a.example", "https://b.example"])
        self.assertEqual(req.selected_provider, "gemini")
        self.assertEqual(req.selected_model, "")
        self.assertTrue(req.dry_run)
        self.assertTrue(req.auto_format_pdf)

    def test_parse_research_run_request_bubbles_validation_errors(self) -> None:
        payload = {
            "selectedProvider": "gemini",
            "selectedModel": "",
            "companyName": "Example Inc",
            "urls": ["https://a.example"],
            "autoFormatPdf": "not-bool",
        }

        with self.assertRaisesRegex(ValueError, "autoFormatPdf must be a boolean"):
            server.parse_research_run_request(payload)

    def test_parse_selected_theme_keeps_known_and_drops_unknown(self) -> None:
        self.assertEqual(parse_selected_theme({"selectedTheme": " compact "}), "compact")
        self.assertEqual(parse_selected_theme({"selectedTheme": "default"}), "default")
        self.assertEqual(parse_selected_theme({"selectedTheme": "../evil"}), "")
        self.assertEqual(parse_selected_theme({}), "")

    def test_make_command_passes_theme_to_both_kinds(self) -> None:
        self.assertEqual(server.make_command("format", theme="compact")[-2:], ["--theme", "compact"])
        self.assertEqual(server.make_command("full", "gemini", "", theme="compact")[-2:], ["--theme", "compact"])
        self.assertNotIn("--theme", server.make_command("format"))
        self.assertNotIn("--theme", server.make_command("full", "gemini"))

    def test_parse_steering_distinguishes_absent_disabled_and_text(self) -> None:
        self.assertIsNone(parse_steering({}))
        self.assertEqual(parse_steering({"steering": {"enabled": False, "text": "AI focus"}}), "")
        self.assertEqual(parse_steering({"steering": {"enabled": True, "text": "   "}}), "")
        self.assertEqual(parse_steering({"steering": {"enabled": True, "text": " AI focus "}}), "AI focus")

    def test_parse_steering_rejects_bad_shapes(self) -> None:
        with self.assertRaisesRegex(ValueError, "steering must be an object"):
            parse_steering({"steering": "AI focus"})
        with self.assertRaisesRegex(ValueError, "steering.enabled must be a boolean"):
            parse_steering({"steering": {"enabled": "yes", "text": ""}})
        with self.assertRaisesRegex(ValueError, "steering.text must be a string"):
            parse_steering({"steering": {"enabled": True, "text": 3}})

    def test_prepare_steering_file_writes_text_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_file = Path(tmp) / "out" / "steering.run.md"
            with mock.patch.object(server_run_helpers, "STEERING_RUN_FILE", run_file):
                self.assertIsNone(server_run_helpers.prepare_steering_file(None))
                self.assertEqual(server_run_helpers.prepare_steering_file(""), "")
                self.assertFalse(run_file.exists())
                self.assertEqual(server_run_helpers.prepare_steering_file("AI focus"), str(run_file))
                self.assertEqual(run_file.read_text(encoding="utf-8"), "AI focus\n")

    def test_make_command_steering_flags_for_full_runs_only(self) -> None:
        self.assertNotIn("--no-steering", server.make_command("full", "gemini"))
        self.assertEqual(server.make_command("full", "gemini", steering_file="")[-1], "--no-steering")
        self.assertEqual(
            server.make_command("full", "gemini", steering_file="/tmp/s.md")[-2:],
            ["--steering-file", "/tmp/s.md"],
        )
        format_command = server.make_command("format", steering_file="/tmp/s.md")
        self.assertNotIn("--steering-file", format_command)
        self.assertNotIn("--no-steering", format_command)

    def test_read_output_steering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tailored.model.json"
            self.assertEqual(read_output_steering(path), "")
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(read_output_steering(path), "")
            path.write_text(json.dumps({"metadata": {"company": "X"}}), encoding="utf-8")
            self.assertEqual(read_output_steering(path), "")
            path.write_text(json.dumps({"metadata": {"steering": " AI focus "}}), encoding="utf-8")
            self.assertEqual(read_output_steering(path), "AI focus")


if __name__ == "__main__":
    unittest.main()
