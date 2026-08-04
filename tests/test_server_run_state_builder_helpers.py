import unittest

from cv_web import server


class ServerRunStateBuilderHelpersTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
