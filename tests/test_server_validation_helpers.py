import unittest

from cv_web import server
from cv_web.server_request_parsing import parse_selected_theme


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


if __name__ == "__main__":
    unittest.main()
