import unittest
from types import SimpleNamespace
from unittest import mock

from cv_web import server


class _DummyHandler:
    def __init__(self) -> None:
        self.responses = []
        self.errors = []
        self.served = []

    def _json_response(self, payload, status=200):
        self.responses.append((status, payload))

    def send_error(self, status, message):
        self.errors.append((status, message))

    def _serve_file(self, path, content_type):
        self.served.append((str(path), content_type))


class ServerGetHandlersTests(unittest.TestCase):
    def test_handle_logs_content_get_requires_name(self) -> None:
        handler = _DummyHandler()
        parsed = SimpleNamespace(query="")

        server.CVWebHandler._handle_logs_content_get(handler, parsed)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "Missing log file name")

    def test_handle_logs_content_get_handles_not_found(self) -> None:
        handler = _DummyHandler()
        parsed = SimpleNamespace(query="name=test.log")

        with mock.patch.object(server, "read_log_file", side_effect=FileNotFoundError):
            server.CVWebHandler._handle_logs_content_get(handler, parsed)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "Log file not found")

    def test_handle_logs_content_get_success(self) -> None:
        handler = _DummyHandler()
        parsed = SimpleNamespace(query="name=test.log")

        with mock.patch.object(server, "read_log_file", return_value="hello"):
            server.CVWebHandler._handle_logs_content_get(handler, parsed)

        self.assertEqual(len(handler.responses), 1)
        status, payload = handler.responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(payload["name"], "test.log")
        self.assertEqual(payload["content"], "hello")

    def test_handle_output_get_rejects_unknown_file(self) -> None:
        handler = _DummyHandler()

        handled = server.CVWebHandler._handle_output_get(handler, "/output/not-allowed.pdf")

        self.assertTrue(handled)
        self.assertEqual(len(handler.errors), 1)
        status, message = handler.errors[0]
        self.assertEqual(status, server.HTTPStatus.NOT_FOUND)
        self.assertEqual(message, "Unknown output file")

    def test_handle_output_get_serves_allowed_pdf(self) -> None:
        handler = _DummyHandler()

        handled = server.CVWebHandler._handle_output_get(handler, "/output/tailored_dev.pdf")

        self.assertTrue(handled)
        self.assertEqual(len(handler.served), 1)
        path, content_type = handler.served[0]
        self.assertTrue(path.endswith("output/tailored_dev.pdf"))
        self.assertEqual(content_type, "application/pdf")

    def test_handle_output_get_returns_false_for_non_output_route(self) -> None:
        handler = _DummyHandler()

        handled = server.CVWebHandler._handle_output_get(handler, "/api/state")

        self.assertFalse(handled)
        self.assertEqual(handler.served, [])
        self.assertEqual(handler.errors, [])


if __name__ == "__main__":
    unittest.main()
