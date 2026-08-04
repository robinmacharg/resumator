import unittest

from cv_web import server


class ServerRunStateBuilderHelpersTests(unittest.TestCase):
    def test_build_research_command_includes_provider_model_urls_and_dry_run(self) -> None:
        command = server._build_research_command(
            company_name="Acme",
            urls=["https://example.com", "https://example.org"],
            dry_run=True,
            selected_provider="gemini",
            selected_model="gpt-5",
        )

        self.assertEqual(command[0], server.sys.executable)
        self.assertIn("research_role.py", command[1])
        self.assertEqual(command[2:4], ["--company-name", "Acme"])
        self.assertIn("--model", command)
        self.assertIn("gpt-5", command)
        self.assertIn("--provider", command)
        self.assertIn("gemini", command)
        self.assertEqual(command.count("--url"), 2)
        self.assertEqual(command[-1], "--dry-run")

    def test_build_research_command_omits_optional_flags_when_not_set(self) -> None:
        command = server._build_research_command(
            company_name="Acme",
            urls=[],
            dry_run=False,
        )

        self.assertEqual(command[0], server.sys.executable)
        self.assertIn("research_role.py", command[1])
        self.assertNotIn("--model", command)
        self.assertNotIn("--provider", command)
        self.assertNotIn("--url", command)
        self.assertNotIn("--dry-run", command)

    def test_build_research_format_command_targets_format_script(self) -> None:
        command = server._build_research_format_command()

        self.assertEqual(command[0], server.sys.executable)
        self.assertIn("research_format.py", command[1])

    def test_build_run_state_includes_runtime_fields_and_mtimes(self) -> None:
        run_state = server._build_run_state(
            kind="full",
            command=["python", "generate_cv.py"],
            selected_provider="gemini",
            selected_model="gpt-5",
            exit_code=None,
            started_at="start",
            finished_at=None,
            elapsed_seconds=0.0,
            success=None,
            running=True,
            output="",
            started_monotonic=123.45,
        )

        self.assertEqual(run_state["kind"], "full")
        self.assertEqual(run_state["command"], ["python", "generate_cv.py"])
        self.assertEqual(run_state["selectedProvider"], "gemini")
        self.assertEqual(run_state["selectedModel"], "gpt-5")
        self.assertTrue(run_state["running"])
        self.assertIn("pdfMtime", run_state)
        self.assertIn("docxMtime", run_state)
        self.assertEqual(run_state["_startedMonotonic"], 123.45)

    def test_build_run_state_omits_internal_timer_for_terminal_state(self) -> None:
        run_state = server._build_run_state(
            kind="format",
            command=["python", "cv_convert.py"],
            selected_provider="",
            selected_model="",
            exit_code=1,
            started_at="start",
            finished_at="finish",
            elapsed_seconds=1.25,
            success=False,
            running=False,
            output="failed",
        )

        self.assertEqual(run_state["kind"], "format")
        self.assertEqual(run_state["exitCode"], 1)
        self.assertFalse(run_state["running"])
        self.assertFalse(run_state["success"])
        self.assertEqual(run_state["output"], "failed")
        self.assertNotIn("_startedMonotonic", run_state)

    def test_build_research_run_state_includes_expected_fields(self) -> None:
        run_state = server._build_research_run_state(
            command=["python", "research_role.py"],
            company_name="Acme",
            urls=["https://example.com"],
            dry_run=False,
            auto_format_pdf=True,
            selected_provider="gemini",
            selected_model="gpt-5",
            exit_code=None,
            started_at="start",
            finished_at=None,
            elapsed_seconds=0.0,
            success=None,
            running=True,
            output="",
            started_monotonic=10.0,
        )

        self.assertEqual(run_state["kind"], "research")
        self.assertEqual(run_state["companyName"], "Acme")
        self.assertEqual(run_state["urls"], ["https://example.com"])
        self.assertTrue(run_state["autoFormatPdf"])
        self.assertEqual(run_state["selectedProvider"], "gemini")
        self.assertEqual(run_state["selectedModel"], "gpt-5")
        self.assertFalse(run_state["formatAttempted"])
        self.assertIsNone(run_state["formatSuccess"])
        self.assertIsNone(run_state["formatExitCode"])
        self.assertEqual(run_state["_startedMonotonic"], 10.0)

    def test_build_research_format_state_adds_pdf_mtime(self) -> None:
        run_state = server._build_research_format_state(
            command=["python", "research_format.py"],
            exit_code=1,
            started_at="start",
            finished_at="finish",
            elapsed_seconds=1.0,
            success=False,
            running=False,
            output="failed",
        )

        self.assertEqual(run_state["kind"], "research_format")
        self.assertIn("formattedPdfMtime", run_state)
        self.assertEqual(run_state["output"], "failed")
        self.assertNotIn("_startedMonotonic", run_state)


if __name__ == "__main__":
    unittest.main()
