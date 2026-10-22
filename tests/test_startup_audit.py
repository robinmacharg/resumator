import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv_convert
import generate_cv
import research_format
import research_role
import resumator
import startup_audit
from cv_web import server


class AuditCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.home = home
        self.enterContext(mock.patch.object(Path, "home", return_value=home))
        self.enterContext(mock.patch.dict(os.environ, {}, clear=True))

    def codes(self, **kwargs) -> list[str]:
        return [f.code for f in startup_audit.run_audit(self.root, **kwargs)]


class CheckTests(AuditCase):
    def test_clean_install_has_no_findings(self) -> None:
        self.assertEqual(startup_audit.run_audit(self.root), [])

    def test_dotenv_is_an_error_with_import_command(self) -> None:
        (self.root / ".env").write_text("X=1\n")
        (self.root / "sub").mkdir()
        (self.root / "sub" / ".env.local").write_text("X=1\n")
        findings = startup_audit.run_audit(self.root)
        self.assertEqual([f.level for f in findings], ["error", "error"])
        self.assertIn("settings-import --env-file", findings[0].message)

    def test_dotenv_skips_vendored_folders(self) -> None:
        for folder in (".venv", "node_modules", "VSCodeExtension/runtime", ".git"):
            path = self.root / folder
            path.mkdir(parents=True)
            (path / ".env").write_text("X=1\n")
        (self.root / "VSCodeExtension" / "other").mkdir()
        self.assertEqual(self.codes(), [])
        (self.root / "VSCodeExtension" / "other" / ".env").write_text("X=1\n")
        self.assertEqual(self.codes(), ["dotenv"])

    def test_example_env_name_is_not_matched(self) -> None:
        (self.root / "settings.example.env").write_text("X=1\n")
        self.assertEqual(self.codes(), [])

    def test_allow_skips_dotenv(self) -> None:
        (self.root / ".env").write_text("X=1\n")
        self.assertEqual(self.codes(allow={"dotenv"}), [])

    def test_model_providers_json_warns(self) -> None:
        (self.root / "model_providers.json").write_text("{}")
        findings = startup_audit.run_audit(self.root)
        self.assertEqual([(f.level, f.code) for f in findings], [("warn", "model-providers")])

    def test_gemini_home_env_warns(self) -> None:
        (self.home / ".gemini").mkdir()
        (self.home / ".gemini" / ".env").write_text("X=1\n")
        findings = startup_audit.run_audit(self.root)
        self.assertEqual([(f.level, f.code) for f in findings], [("warn", "gemini-home-env")])

    def test_shell_shadow_warns_and_names_keys_only(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sekrit", "PATH": "/bin"}):
            findings = startup_audit.run_audit(self.root)
        self.assertEqual([(f.level, f.code) for f in findings], [("warn", "shell-shadow")])
        self.assertIn("OPENAI_API_KEY", findings[0].message)
        self.assertNotIn("sekrit", findings[0].message)


class AuditOrExitTests(AuditCase):
    def test_error_exits_nonzero_and_prints(self) -> None:
        (self.root / ".env").write_text("X=1\n")
        with mock.patch("sys.stderr") as err, self.assertRaises(SystemExit) as ctx:
            startup_audit.audit_or_exit(self.root)
        self.assertEqual(ctx.exception.code, 1)
        self.assertTrue(err.write.called)

    def test_warning_only_returns(self) -> None:
        (self.root / "model_providers.json").write_text("{}")
        with mock.patch("sys.stderr"):
            startup_audit.audit_or_exit(self.root)

    def test_allow_lets_import_through(self) -> None:
        (self.root / ".env").write_text("X=1\n")
        startup_audit.audit_or_exit(self.root, allow={"dotenv"})


class EntryPointTests(unittest.TestCase):
    """Each entry point audits before doing anything else; an error stops it."""

    def failing(self):
        err = [startup_audit.Finding("error", "dotenv", "stray .env")]
        return mock.patch.object(startup_audit, "run_audit", return_value=err)

    def test_entry_points_refuse(self) -> None:
        def boom(*a, **k):
            raise AssertionError("ran past the audit")

        cases = [
            (server.run_server, [], {"ThreadingHTTPServer": boom}, server),
            (generate_cv.main, ["generate_cv.py"], {"run_cv": boom}, generate_cv),
            (research_role.main, ["research_role.py"], {"run_research": boom}, research_role),
            (research_format.main, ["research_format.py"], {"run": boom}, research_format),
            (cv_convert.main, ["cv_convert.py"], {"convert_markdown_outputs": boom}, cv_convert),
            (resumator.main, None, {"_list": boom}, resumator),
        ]
        for fn, argv, patches, module in cases:
            with self.subTest(fn.__module__), self.failing(), mock.patch("sys.stderr"):
                with mock.patch.multiple(module, **patches):
                    if argv is None:
                        call = lambda: fn(["--action", "list"])
                    else:
                        call = fn
                    with mock.patch("sys.argv", argv), self.assertRaises(SystemExit) as ctx:
                        call()
                self.assertEqual(ctx.exception.code, 1)

    def test_resumator_import_action_allows_dotenv(self) -> None:
        with mock.patch.object(startup_audit, "audit_or_exit") as audit, \
                mock.patch.object(resumator, "build_parser") as bp:
            bp.return_value.parse_args.return_value = mock.Mock(action="settings-import", role=None, choice=None, db=":memory:")
            with mock.patch.object(resumator, "ACTION_HANDLERS", {"settings-import": lambda c, a: 0}):
                resumator.main([])
        audit.assert_called_once_with(allow={"dotenv"})


if __name__ == "__main__":
    unittest.main()
