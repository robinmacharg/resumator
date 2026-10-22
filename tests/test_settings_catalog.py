import re
import unittest
from pathlib import Path
from unittest import mock

import settings_catalog
from backends.base import BackendStatus, SettingSpec, TestResult
from provider_clients import AttemptResult

ROOT = Path(__file__).resolve().parent.parent
KEY = r"([A-Z][A-Z0-9_]{3,})"
READ_PATTERNS = [
    re.compile(rf'(?:env|process_env|os\.environ|\))\.get\(\s*"{KEY}"'),
    re.compile(rf'parse_positive_int\(\s*\w+,\s*"{KEY}"'),
]
SOURCES = [
    path
    for path in [*ROOT.glob("*.py"), *ROOT.glob("backends/*/module.py")]
    if not path.name.startswith("gemini-code") and path.name != "settings_catalog.py"
]
# Read from the real process environment, not user config.
NOT_CONFIG = {"PATH", "HOME"}


class FakeBackend:
    id = "fake"
    label = "Fake"
    timeout_seconds = 300

    def __init__(self, enabled=True, attempt=None):
        self.enabled = enabled
        self.attempt = attempt
        self.calls = []

    def interrogate(self, env):
        return BackendStatus(enabled=self.enabled, reason="" if self.enabled else "no key", models=["m1", "m2"])

    def model_sequence(self, env, explicit_model=""):
        return ["m1", "m2"]

    def run_attempt(self, **kwargs):
        self.calls.append(kwargs)
        return self.attempt


def attempt(returncode=0, stdout="OK", stderr="", timed_out=False):
    return AttemptResult("fake", "m1", returncode, stdout, stderr, 0.5, None, timed_out)


class CatalogKeyTests(unittest.TestCase):
    def test_every_key_read_in_code_is_declared(self) -> None:
        declared = settings_catalog.catalog_keys()
        missing = {}
        seen = set()
        for path in SOURCES:
            text = path.read_text(encoding="utf-8")
            for pattern in READ_PATTERNS:
                for key in pattern.findall(text):
                    seen.add(key)
                    if key not in declared and key not in NOT_CONFIG:
                        missing.setdefault(key, path.name)
        self.assertEqual(missing, {})
        self.assertTrue({"OPENAI_API_KEY", "RESEARCH_GEMINI_TIMEOUT_SECONDS", "CV_THEME"} <= seen)

    def test_secrets_are_flagged(self) -> None:
        secrets = {
            spec.key
            for group in settings_catalog.catalog()
            for spec in group.specs
            if spec.secret
        }
        self.assertTrue(
            {"OPENAI_API_KEY", "HF_API_TOKEN", "GEMINI_API_KEY", "VSCODE_BRIDGE_API_KEY"} <= secrets
        )
        for group in settings_catalog.catalog():
            for spec in group.specs:
                if spec.key.endswith(("_API_KEY", "_TOKEN")):
                    self.assertTrue(spec.secret, spec.key)

    def test_groups_are_global_then_backends(self) -> None:
        ids = [group.id for group in settings_catalog.catalog()]
        self.assertEqual(ids[0], "global")
        self.assertTrue({"openai", "gemini", "swiftlet", "claudecode"} <= set(ids))
        self.assertNotIn("other", ids)

    def test_unknown_stored_keys_land_in_other(self) -> None:
        groups = settings_catalog.catalog({"OPENAI_API_KEY": "x", "SOMETHING_ELSE": "y", "A_KEY": "z"})
        other = groups[-1]
        self.assertEqual(other.id, "other")
        self.assertEqual([spec.key for spec in other.specs], ["A_KEY", "SOMETHING_ELSE"])

    def test_keys_are_unique(self) -> None:
        keys = [spec.key for group in settings_catalog.catalog() for spec in group.specs]
        self.assertEqual(len(keys), len(set(keys)))


class DefaultTestConnectionTests(unittest.TestCase):
    def test_ok(self) -> None:
        backend = FakeBackend(attempt=attempt())
        result = settings_catalog.default_test_connection(backend, {})
        self.assertEqual((result.ok, result.message, result.model), (True, "OK", "m1"))
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(backend.calls[0]["model_name"], "m1")
        self.assertEqual(backend.calls[0]["timeout_seconds"], settings_catalog.TEST_TIMEOUT_SECONDS)

    def test_disabled_backend_skips_the_call(self) -> None:
        backend = FakeBackend(enabled=False)
        result = settings_catalog.default_test_connection(backend, {})
        self.assertEqual((result.ok, result.message), (False, "no key"))
        self.assertEqual(backend.calls, [])

    def test_failure_reports_last_stderr_line(self) -> None:
        backend = FakeBackend(attempt=attempt(returncode=401, stdout="", stderr="warn\nHTTP 401: bad key"))
        result = settings_catalog.default_test_connection(backend, {})
        self.assertEqual((result.ok, result.message), (False, "HTTP 401: bad key"))

    def test_timeout(self) -> None:
        backend = FakeBackend(attempt=attempt(returncode=1, stdout="", timed_out=True))
        self.assertEqual(settings_catalog.default_test_connection(backend, {}).message, "timed out")

    def test_exception_is_a_failed_result(self) -> None:
        backend = FakeBackend()
        backend.run_attempt = mock.Mock(side_effect=RuntimeError("boom"))
        result = settings_catalog.default_test_connection(backend, {})
        self.assertEqual((result.ok, result.message), (False, "RuntimeError: boom"))

    def test_backend_override_is_used(self) -> None:
        backend = FakeBackend()
        backend.test_connection = lambda env: TestResult(True, "custom")
        self.assertEqual(settings_catalog.test_connection(backend, {}).message, "custom")
        self.assertEqual(backend.calls, [])

    def test_dispatch_falls_back_to_default(self) -> None:
        backend = FakeBackend(attempt=attempt())
        self.assertTrue(settings_catalog.test_connection(backend, {}).ok)


if __name__ == "__main__":
    unittest.main()
