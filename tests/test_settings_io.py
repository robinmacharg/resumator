"""Tests for settings_io (import/export core) and the settings-* role CLI actions, on a temp DB."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import resumator  # noqa: E402
import settings_io  # noqa: E402
from backends.base import TestResult  # noqa: E402
from cv_web import store  # noqa: E402


class DbCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.db = self.tmp / "test.db"
        self.conn = store.connect(self.db)
        self.addCleanup(self.conn.close)


class ImportTests(DbCase):
    def test_merge_diff_and_write(self) -> None:
        store.set_env_setting(self.conn, "CV_THEME", "default")
        store.set_env_setting(self.conn, "OLD", "x")
        diff = settings_io.env_import(self.conn, "CV_THEME=compact\nNEW=1\n", "merge")
        self.assertEqual(diff, {"added": ["NEW"], "changed": ["CV_THEME"], "unchanged": [], "removed": []})
        self.assertEqual(store.env_settings(self.conn), {"CV_THEME": "compact", "NEW": "1", "OLD": "x"})

    def test_replace_removes_and_dry_run_writes_nothing(self) -> None:
        store.set_env_setting(self.conn, "OLD", "x")
        store.set_env_setting(self.conn, "KEEP", "1")
        diff = settings_io.env_import(self.conn, "KEEP=1\nNEW=2", "replace", dry_run=True)
        self.assertEqual(diff, {"added": ["NEW"], "changed": [], "unchanged": ["KEEP"], "removed": ["OLD"]})
        self.assertEqual(store.env_settings(self.conn), {"OLD": "x", "KEEP": "1"})
        settings_io.env_import(self.conn, "KEEP=1\nNEW=2", "replace")
        self.assertEqual(store.env_settings(self.conn), {"KEEP": "1", "NEW": "2"})

    def test_bad_mode_and_key(self) -> None:
        with self.assertRaises(ValueError):
            settings_io.env_import(self.conn, "A=1", "nope")
        with self.assertRaises(ValueError):
            settings_io.env_import(self.conn, "BAD-KEY=1")

    def test_quoting_and_export_lines(self) -> None:
        diff = settings_io.env_import(self.conn, "export A='x y'\nB=\"q # r\"\nC=plain")
        self.assertEqual(diff["added"], ["A", "B", "C"])
        self.assertEqual(store.env_settings(self.conn), {"A": "x y", "B": "q # r", "C": "plain"})

    def test_from_environment_takes_only_catalogued_keys(self) -> None:
        got = settings_io.env_from_environment({"OPENAI_API_KEY": "k", "PATH": "/bin", "CV_THEME": ""})
        self.assertEqual(got, {"OPENAI_API_KEY": "k"})


class ExportTests(DbCase):
    def seed(self) -> None:
        settings_io.env_import(
            self.conn,
            'OPENAI_API_KEY=sk-secret-value-1234\nCV_FONT_PRIORITY="Fira Code,Arial"\nGEMINI_API_KEY=AIza-abcdefgh-9999\nZZ=1',
        )

    def test_masks_secrets_and_groups(self) -> None:
        self.seed()
        text = settings_io.env_export(self.conn)
        self.assertNotIn("sk-secret-value-1234", text)
        self.assertNotIn("AIza-abcdefgh-9999", text)  # unknown but secret-looking
        self.assertIn("OPENAI_API_KEY=sk-…1234", text)
        self.assertIn("# Global", text)
        self.assertIn("# Other", text)
        self.assertIn('CV_FONT_PRIORITY="Fira Code,Arial"', text)

    def test_reveal_round_trips_through_import(self) -> None:
        self.seed()
        before = store.env_settings(self.conn)
        text = settings_io.env_export(self.conn, reveal=True)
        other = store.connect(self.tmp / "other.db")
        self.addCleanup(other.close)
        settings_io.env_import(other, text)
        self.assertEqual(store.env_settings(other), before)

    def test_masked_export_does_not_overwrite_secrets(self) -> None:
        self.seed()
        before = store.env_settings(self.conn)
        diff = settings_io.env_import(self.conn, settings_io.env_export(self.conn))
        self.assertEqual(store.env_settings(self.conn), before)
        self.assertEqual(diff["changed"], [])

    def test_empty(self) -> None:
        self.assertEqual(settings_io.env_export(self.conn), "")

    def test_sample_file_imports_and_has_no_real_keys(self) -> None:
        sample = (ROOT_DIR / "examples" / "settings.example.env").read_text(encoding="utf-8")
        diff = settings_io.env_import(self.conn, sample)
        self.assertIn("OPENAI_API_KEY", diff["added"])
        self.assertIn("not-a-real-key", store.env_settings(self.conn)["OPENAI_API_KEY"])


class CliTests(DbCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(mock.patch.object(resumator.startup_audit, "run_audit", return_value=[]))

    def cli(self, *args: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            try:
                code = resumator.main(["--db", str(self.db), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_import_file_dry_run_then_real_then_delete_after(self) -> None:
        env_file = self.tmp / "legacy.env"
        env_file.write_text("OPENAI_API_KEY=sk-abc-123456\nCV_THEME=compact\n", encoding="utf-8")
        code, out, _ = self.cli("--action", "settings-import", "--env-file", str(env_file), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("added: 2", out)
        self.assertNotIn("sk-abc-123456", out)
        self.assertEqual(store.env_settings(self.conn), {})
        code, out, _ = self.cli("--action", "settings-import", "--env-file", str(env_file), "--delete-after")
        self.assertEqual(code, 0)
        self.assertFalse(env_file.exists())
        self.assertEqual(store.env_settings(self.conn)["CV_THEME"], "compact")

    def test_import_replace_and_from_environment(self) -> None:
        store.set_env_setting(self.conn, "OLD", "1")
        with mock.patch.dict("os.environ", {"CV_THEME": "compact"}):
            code, out, _ = self.cli("--action", "settings-import", "--from-environment", "--replace")
        self.assertEqual(code, 0)
        self.assertIn("removed: 1", out)
        self.assertEqual(store.env_settings(self.conn), {"CV_THEME": "compact"})

    def test_import_needs_one_source(self) -> None:
        code, _, err = self.cli("--action", "settings-import")
        self.assertEqual(code, 2)
        self.assertIn("exactly one", err)

    def test_import_audit_allows_dotenv_only_for_import(self) -> None:
        with mock.patch.object(resumator.startup_audit, "audit_or_exit") as audit:
            self.cli("--action", "settings-import", "--from-environment")
            self.assertEqual(set(audit.call_args.kwargs["allow"]), {"dotenv"})
            self.cli("--action", "settings-export")
            self.assertEqual(tuple(audit.call_args.kwargs["allow"]), ())

    def test_export_masks_unless_reveal(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", "sk-secret-value-1234")
        _, out, _ = self.cli("--action", "settings-export")
        self.assertIn("sk-…1234", out)
        self.assertNotIn("sk-secret-value-1234", out)
        _, out, _ = self.cli("--action", "settings-export", "--reveal")
        self.assertIn("OPENAI_API_KEY=sk-secret-value-1234", out)

    def test_export_empty(self) -> None:
        code, out, _ = self.cli("--action", "settings-export")
        self.assertEqual((code, out.strip()), (0, "# No settings stored."))

    def test_set_secret_uses_getpass_and_plain_uses_stdin(self) -> None:
        with mock.patch.object(resumator.getpass, "getpass", return_value="sk-typed-9999") as ask:
            code, out, _ = self.cli("--action", "settings-set", "--key", "OPENAI_API_KEY")
        self.assertEqual(code, 0)
        ask.assert_called_once()
        self.assertNotIn("sk-typed-9999", out)
        code, _, _ = self.cli("--action", "settings-set", "--key", "CV_THEME", stdin="compact\n")
        self.assertEqual(code, 0)
        self.assertEqual(store.env_settings(self.conn), {"OPENAI_API_KEY": "sk-typed-9999", "CV_THEME": "compact"})

    def test_set_rejects_empty_value_and_bad_key(self) -> None:
        self.assertEqual(self.cli("--action", "settings-set", "--key", "CV_THEME", stdin="\n")[0], 1)
        self.assertEqual(self.cli("--action", "settings-set", "--key", "bad-key", stdin="x")[0], 1)

    def test_test_action(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_API_KEY", "sk-x")
        with mock.patch.object(resumator.settings_catalog, "test_connection",
                               return_value=TestResult(True, "OK", 1.2, "m1")) as run:
            code, out, _ = self.cli("--action", "settings-test", "--provider", "openai")
        self.assertEqual(code, 0)
        self.assertIn("OK (m1, 1.2s)", out)
        self.assertEqual(run.call_args.args[1]["OPENAI_API_KEY"], "sk-x")
        with mock.patch.object(resumator.settings_catalog, "test_connection",
                               return_value=TestResult(False, "bad key")):
            code, _, err = self.cli("--action", "settings-test", "--provider", "openai")
        self.assertEqual(code, 1)
        self.assertIn("bad key", err)
        self.assertEqual(self.cli("--action", "settings-test", "--provider", "nope")[0], 1)


if __name__ == "__main__":
    unittest.main()
