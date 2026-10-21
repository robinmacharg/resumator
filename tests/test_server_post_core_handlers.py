import unittest
from unittest import mock

from cv_web import server


class _DummyHandler:
    def __init__(self) -> None:
        self.responses = []

    def _json_response(self, payload, status=200):
        self.responses.append((status, payload))


class _FakeLock:
    def __init__(self, acquire_result: bool) -> None:
        self.acquire_result = acquire_result
        self.release_calls = 0

    def acquire(self, blocking=False):
        return self.acquire_result

    def release(self):
        self.release_calls += 1


class _FakeThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True


class _FakePath:
    def __init__(self, exists_value: bool, name: str = "research_prompt.default.md") -> None:
        self._exists_value = exists_value
        self.name = name

    def exists(self):
        return self._exists_value


class ServerPostCoreHandlersTests(unittest.TestCase):
    def test_handle_save_returns_400_on_payload_error(self) -> None:
        handler = _DummyHandler()
        handler._save_editor_payload = mock.Mock(side_effect=ValueError("bad payload"))

        server.CVWebHandler._handle_save(handler, {})

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "bad payload")

    def test_handle_server_restart_returns_success(self) -> None:
        handler = _DummyHandler()

        with mock.patch.object(server, "schedule_process_restart"):
            with mock.patch.object(server, "utc_now_iso", return_value="now"):
                server.CVWebHandler._handle_server_restart(handler)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["restarting"])
        self.assertEqual(payload["requestedAt"], "now")

    def test_handle_research_reset_prompt_returns_404_when_default_missing(self) -> None:
        handler = _DummyHandler()

        with mock.patch.object(server, "RESEARCH_PROMPT_DEFAULT_FILE", _FakePath(False)):
            server.CVWebHandler._handle_research_reset_prompt(handler)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 404)
        self.assertIn("Default research prompt not found", payload["error"])

    def test_handle_cv_run_returns_409_when_run_lock_busy(self) -> None:
        handler = _DummyHandler()
        handler._save_editor_payload = mock.Mock()
        fake_lock = _FakeLock(acquire_result=False)

        req = server.CvRunRequest(kind="full", selected_provider="gemini", selected_model="")

        with mock.patch.object(server, "parse_cv_run_request", return_value=req):
            with mock.patch.object(server, "RUN_LOCK", fake_lock):
                server.CVWebHandler._handle_cv_run(handler, "/api/run/full", {})

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "A run is already in progress")

    def test_handle_cv_run_success_response(self) -> None:
        handler = _DummyHandler()
        handler._save_editor_payload = mock.Mock()
        fake_lock = _FakeLock(acquire_result=True)

        req = server.CvRunRequest(kind="format", selected_provider="gemini", selected_model="")

        with mock.patch.object(server, "parse_cv_run_request", return_value=req):
            with mock.patch.object(server, "RUN_LOCK", fake_lock):
                with mock.patch.object(server.threading, "Thread", _FakeThread):
                    with mock.patch.object(server, "get_current_run_snapshot", return_value={"running": True}):
                        with mock.patch.object(server, "build_state", return_value={"state": "ok"}):
                            server.CVWebHandler._handle_cv_run(handler, "/api/run/format", {})

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["running"])
        self.assertEqual(payload["run"], {"running": True})
        self.assertEqual(payload["state"], {"state": "ok"})


    def test_handle_cv_run_passes_theme_to_the_run_thread(self) -> None:
        handler = _DummyHandler()
        handler._save_editor_payload = mock.Mock()
        threads = []

        class _CapturingThread(_FakeThread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                threads.append(self)

        req = server.CvRunRequest(kind="format", selected_provider="gemini", selected_model="", theme="compact")

        with mock.patch.object(server, "parse_cv_run_request", return_value=req):
            with mock.patch.object(server, "RUN_LOCK", _FakeLock(acquire_result=True)):
                with mock.patch.object(server.threading, "Thread", _CapturingThread):
                    with mock.patch.object(server, "get_current_run_snapshot", return_value={}):
                        with mock.patch.object(server, "build_state", return_value={}):
                            server.CVWebHandler._handle_cv_run(handler, "/api/run/format", {})

        self.assertEqual(threads[0].kwargs["args"], ("format", "gemini", "", "compact", None))


    def test_handle_cv_run_prepares_steering_for_full_runs(self) -> None:
        handler = _DummyHandler()
        handler._save_editor_payload = mock.Mock()
        threads = []

        class _CapturingThread(_FakeThread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                threads.append(self)

        req = server.CvRunRequest(
            kind="full", selected_provider="gemini", selected_model="", theme="", steering="AI focus"
        )
        prepare = mock.Mock(return_value="/tmp/steering.run.md")

        with mock.patch.object(server, "parse_cv_run_request", return_value=req):
            with mock.patch.object(server, "prepare_steering_file", prepare):
                with mock.patch.object(server, "RUN_LOCK", _FakeLock(acquire_result=True)):
                    with mock.patch.object(server.threading, "Thread", _CapturingThread):
                        with mock.patch.object(server, "get_current_run_snapshot", return_value={}):
                            with mock.patch.object(server, "build_state", return_value={}):
                                server.CVWebHandler._handle_cv_run(handler, "/api/run/full", {})

        prepare.assert_called_once_with("AI focus")
        self.assertEqual(threads[0].kwargs["args"], ("full", "gemini", "", "", "/tmp/steering.run.md"))


if __name__ == "__main__":
    unittest.main()
