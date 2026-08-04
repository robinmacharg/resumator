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


class ServerPostResearchHandlersTests(unittest.TestCase):
    def test_handle_research_format_returns_409_when_lock_busy(self) -> None:
        handler = _DummyHandler()
        fake_lock = _FakeLock(acquire_result=False)

        with mock.patch.object(server, "RESEARCH_RUN_LOCK", fake_lock):
            server.CVWebHandler._handle_research_format(handler)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "A research operation is already in progress")

    def test_handle_research_format_returns_success_payload(self) -> None:
        handler = _DummyHandler()
        fake_lock = _FakeLock(acquire_result=True)

        with mock.patch.object(server, "RESEARCH_RUN_LOCK", fake_lock):
            with mock.patch.object(server.threading, "Thread", _FakeThread):
                with mock.patch.object(server, "get_current_research_run_snapshot", return_value={"running": True}):
                    with mock.patch.object(server, "build_research_state", return_value={"state": "ok"}):
                        server.CVWebHandler._handle_research_format(handler)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["running"])
        self.assertEqual(payload["run"], {"running": True})
        self.assertEqual(payload["state"], {"state": "ok"})

    def test_handle_research_stop_requires_active_run(self) -> None:
        handler = _DummyHandler()

        with mock.patch.object(server, "get_current_research_run_snapshot", return_value=None):
            server.CVWebHandler._handle_research_stop(handler)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "No active research run to stop")

    def test_handle_research_stop_returns_success_when_stop_requested(self) -> None:
        handler = _DummyHandler()

        with mock.patch.object(server, "get_current_research_run_snapshot", side_effect=[{"running": True}, {"running": True}]):
            with mock.patch.object(server, "request_stop_research_run", return_value=True):
                server.CVWebHandler._handle_research_stop(handler)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["stopping"])
        self.assertEqual(payload["run"], {"running": True})


if __name__ == "__main__":
    unittest.main()
