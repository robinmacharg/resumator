import unittest
from unittest import mock

from cv_web import server


class _AcquiredLock:
    def release(self) -> None:
        return None


class ServerAsyncFinalizeHelpersTests(unittest.TestCase):
    def test_finalize_run_error_state_updates_last_run_and_clears_current(self) -> None:
        run_state = {
            "kind": "full",
            "running": False,
            "success": False,
            "output": "error",
        }

        server.CURRENT_RUN.clear()
        server.LAST_RUN.clear()

        server._finalize_run_error_state(run_state)

        self.assertEqual(server.CURRENT_RUN, {})
        self.assertEqual(server.LAST_RUN.get("kind"), "full")
        self.assertEqual(server.LAST_RUN.get("output"), "error")

    def test_finalize_research_run_error_state_updates_last_and_clears_current(self) -> None:
        run_state = {
            "kind": "research",
            "running": False,
            "success": False,
            "output": "error",
        }

        server.CURRENT_RESEARCH_RUN.clear()
        server.LAST_RESEARCH_RUN.clear()

        server._finalize_research_run_error_state(run_state)

        self.assertEqual(server.CURRENT_RESEARCH_RUN, {})
        self.assertEqual(server.LAST_RESEARCH_RUN.get("kind"), "research")
        self.assertEqual(server.LAST_RESEARCH_RUN.get("output"), "error")

    def test_run_subprocess_async_uses_finalize_helper_on_failure(self) -> None:
        with mock.patch.object(server, "run_subprocess_streaming", side_effect=RuntimeError("boom")):
            with mock.patch.object(server, "_finalize_run_error_state") as finalize_mock:
                with mock.patch.object(server, "RUN_LOCK", _AcquiredLock()):
                    server.run_subprocess_async("full", "gemini", "")

        finalize_mock.assert_called_once()

    def test_run_research_async_uses_finalize_helper_on_failure(self) -> None:
        with mock.patch.object(server, "run_research_subprocess_streaming", side_effect=RuntimeError("boom")):
            with mock.patch.object(server, "_finalize_research_run_error_state") as finalize_mock:
                with mock.patch.object(server, "RESEARCH_RUN_LOCK", _AcquiredLock()):
                    server.run_research_subprocess_async(
                        company_name="Acme",
                        urls=["https://example.com"],
                        dry_run=False,
                        auto_format_pdf=True,
                        selected_provider="gemini",
                        selected_model="",
                    )

        finalize_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
