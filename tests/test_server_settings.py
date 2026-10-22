"""Tests for cv_web/server_settings.py: the settings API over a temp DB (provider tests are patched)."""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
for path in (ROOT_DIR, ROOT_DIR / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backends.base import TestResult  # noqa: E402
from cv_web import server_roles, server_settings, store  # noqa: E402
from test_server_roles import _Handler  # noqa: E402

SECRET = "sk-secret-value-1234"


class SettingsApiCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = Path(tmp.name) / "test.db"
        self.enterContext(mock.patch.object(server_roles, "DB_PATH", db_path))
        self.conn = store.connect(db_path)
        self.addCleanup(self.conn.close)
        self.deps = {"RUN_LOCK": threading.Lock(), "RESEARCH_RUN_LOCK": threading.Lock()}

    def call(self, method, path, payload=None, query="", status=200):
        handler = _Handler()
        handled = server_roles.dispatch(handler, method, SimpleNamespace(path=path, query=query), payload, self.deps)
        self.assertTrue(handled, path)
        code, body = handler.responses[-1]
        self.assertEqual(code, status, body)
        return body

    def find(self, body, key):
        return next(s for g in body["groups"] for s in g["settings"] if s["key"] == key)


class ReadTests(SettingsApiCase):
    def test_get_groups_with_masked_secrets(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", SECRET)
        store.set_env_setting(self.conn, "CV_THEME", "compact")
        store.set_env_setting(self.conn, "MY_SERVICE_TOKEN", "AIza-abcdefgh-9999")
        body = self.call("GET", "/api/settings")
        labels = [g["id"] for g in body["groups"]]
        self.assertEqual(labels[0], "global")
        self.assertEqual(labels[-1], "other")
        key = self.find(body, "OPENAI_API_KEY")
        self.assertEqual((key["secret"], key["isSet"], key["value"]), (True, True, "sk-…1234"))
        self.assertTrue(self.find(body, "MY_SERVICE_TOKEN")["secret"])
        self.assertNotIn("AIza-abcdefgh-9999", str(body))
        self.assertNotIn(SECRET, str(body))
        theme = self.find(body, "CV_THEME")
        self.assertEqual((theme["secret"], theme["value"]), (False, "compact"))
        unset = self.find(body, "CV_FAST_MODE")
        self.assertEqual((unset["isSet"], unset["value"]), (False, ""))

    def test_reveal(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", SECRET)
        self.assertEqual(self.call("POST", "/api/settings/reveal", {"key": "OPENAI_API_KEY"})["value"], SECRET)
        self.call("POST", "/api/settings/reveal", {"key": "NOPE"}, status=400)

    def test_env_text_masks_unless_reveal(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", SECRET)
        self.assertNotIn(SECRET, self.call("GET", "/api/settings/env")["text"])
        self.assertIn(SECRET, self.call("GET", "/api/settings/env", query="reveal=1")["text"])

    def test_state_has_no_secrets(self) -> None:
        # /api/state is built from provider status only; nothing in its builders may read stored settings.
        for name in ("server.py", "server_state_helpers.py", "server_runtime_state.py"):
            text = (ROOT_DIR / "cv_web" / name).read_text(encoding="utf-8")
            self.assertNotIn("env_settings", text, name)


class WriteTests(SettingsApiCase):
    def test_put_sets_and_deletes(self) -> None:
        store.set_env_setting(self.conn, "OLD", "1")
        body = self.call("PUT", "/api/settings", {"set": {"CV_THEME": "compact"}, "delete": ["OLD"]})
        self.assertTrue(body["success"])
        self.assertEqual(store.env_settings(self.conn), {"CV_THEME": "compact"})
        self.assertEqual(self.find(body, "CV_THEME")["value"], "compact")

    def test_put_ignores_unchanged_masked_placeholder(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", SECRET)
        self.call("PUT", "/api/settings", {"set": {"OPENAI_API_KEY": "sk-…1234", "CV_THEME": "compact"}})
        self.assertEqual(store.get_env_setting(self.conn, "OPENAI_API_KEY"), SECRET)
        self.call("PUT", "/api/settings", {"set": {"OPENAI_API_KEY": "sk-new-5678"}})
        self.assertEqual(store.get_env_setting(self.conn, "OPENAI_API_KEY"), "sk-new-5678")

    def test_put_validates_and_is_atomic(self) -> None:
        self.call("PUT", "/api/settings", {"set": {"bad-key": "x", "CV_THEME": "compact"}}, status=400)
        self.call("PUT", "/api/settings", {"set": {"A": 1}}, status=400)
        self.call("PUT", "/api/settings", {"delete": "A"}, status=400)
        self.assertEqual(store.env_settings(self.conn), {})

    def test_import_dry_run_then_apply(self) -> None:
        body = self.call("POST", "/api/settings/import", {"text": "A=1\nB=2", "dry_run": True})
        self.assertEqual(body["diff"]["added"], ["A", "B"])
        self.assertEqual(store.env_settings(self.conn), {})
        self.call("POST", "/api/settings/import", {"text": "A=1", "mode": "replace"})
        self.assertEqual(store.env_settings(self.conn), {"A": "1"})
        self.call("POST", "/api/settings/import", {"text": "A=1", "mode": "bogus"}, status=400)
        self.call("POST", "/api/settings/import", {}, status=400)


class TestProviderTests(SettingsApiCase):
    def run_test(self, payload):
        with mock.patch.object(server_settings.settings_catalog, "test_connection",
                               return_value=TestResult(True, "OK", 0.5, "m1")) as run:
            body = self.call("POST", "/api/settings/test", payload)
        return body, run.call_args.args[1]

    def test_uses_saved_plus_unsaved_values(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", SECRET)
        body, env = self.run_test({"provider": "openai", "overrides": {"OPENAI_MODEL": "m2"}})
        self.assertEqual(body, {"ok": True, "message": "OK", "elapsedSeconds": 0.5, "model": "m1"})
        self.assertEqual((env["OPENAI_API_KEY"], env["OPENAI_MODEL"]), (SECRET, "m2"))
        self.assertEqual(store.env_settings(self.conn), {"OPENAI_API_KEY": SECRET})  # nothing saved

    def test_masked_override_keeps_saved_secret_and_blank_unsets(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", SECRET)
        store.set_env_setting(self.conn, "OPENAI_MODEL", "m0")
        _, env = self.run_test({"provider": "openai",
                                "overrides": {"OPENAI_API_KEY": "sk-…1234", "OPENAI_MODEL": ""}})
        self.assertEqual(env["OPENAI_API_KEY"], SECRET)
        self.assertNotIn("OPENAI_MODEL", env)

    def test_unknown_provider(self) -> None:
        self.call("POST", "/api/settings/test", {"provider": "nope"}, status=400)


if __name__ == "__main__":
    unittest.main()
