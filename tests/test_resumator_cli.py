"""Tests for resumator.py, the role-mode CLI, on a temp DB. Role runs are patched (role_runner has its own tests
with real scripts); rendering runs for real when pandoc and typst are installed."""

import base64
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import resumator  # noqa: E402
from cv_web import first_run, role_runner, store  # noqa: E402

HAS_RENDERER = bool(shutil.which("pandoc") and shutil.which("typst"))


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.db = self.tmp / "test.db"
        self.conn = store.connect(self.db)
        self.addCleanup(self.conn.close)
        # The audit scans the real repo (which may hold a .env); its own tests cover it.
        self.enterContext(mock.patch.object(resumator.startup_audit, "run_audit", return_value=[]))

    def cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = resumator.main(["--db", str(self.db), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def example(self) -> dict:
        return first_run.set_up(self.conn, "example")


class SetupListCreateTests(CliTestCase):
    def test_empty_db_points_at_setup(self) -> None:
        code, out, _ = self.cli("--action", "list")
        self.assertEqual(code, 0)
        self.assertIn("--action setup", out)
        code, _, err = self.cli("--action", "create", "--role", "X")
        self.assertEqual(code, 1)
        self.assertIn("no master CV", err)

    def test_setup_then_list(self) -> None:
        code, out, _ = self.cli("--action", "setup", "--choice", "example")
        self.assertEqual(code, 0)
        self.assertIn("lead-ios-engineer", out)
        code, _, err = self.cli("--action", "setup", "--choice", "blank")
        self.assertEqual((code, err.strip()), (1, "error: First-run setup is already done"))
        code, out, _ = self.cli("--action", "list")
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("ID  SLUG"))
        self.assertIn("Northwind Health", lines[1])
        self.assertIn("2026-10-01", lines[1])

    def test_create_seeds_from_the_master(self) -> None:
        self.example()
        spec = self.tmp / "spec.txt"
        spec.write_text("The spec.\n")
        code, out, _ = self.cli("--action", "create", "--role", "Second Role", "--company", "B Ltd",
                                "--jobspec-file", str(spec), "--status", "applied")
        self.assertEqual(code, 0)
        role = store.find_role(self.conn, "second-role")
        self.assertEqual((role["company"], role["jobspec"], role["status"]), ("B Ltd", "The spec.\n", "applied"))
        self.assertEqual(store.current_cv_version(self.conn, role["id"])["source"], "seed")
        self.assertIn("slug second-role", out)

    def test_usage_errors(self) -> None:
        self.assertEqual(self.cli("--action", "cv")[0], 2)
        self.assertEqual(self.cli("--action", "setup")[0], 2)
        self.assertEqual(self.cli("--action", "nope")[0], 2)
        self.assertEqual(self.cli("--action", "cv", "--no-steering", "--steering-file", "f")[0], 2)

    def test_backup(self) -> None:
        code, out, _ = self.cli("--action", "backup", "--dest", str(self.tmp / "backups"))
        self.assertEqual(code, 0)
        self.assertEqual(len(list((self.tmp / "backups").glob("resumator-*.db"))), 1)


class RunTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.role_id = self.example()["roleId"]

    def outcome(self, success=True, **result) -> role_runner.RunOutcome:
        return role_runner.RunOutcome(41, success, None if success else "boom", "log", result,
                                      base64.b64encode(b"%PDF-fake").decode() if success else None)

    def test_cv_passes_the_options_and_writes_the_pdf(self) -> None:
        steering = self.tmp / "steer.md"
        steering.write_text("lead with accessibility")
        out_path = self.tmp / "out" / "cv.pdf"
        with mock.patch.object(role_runner, "run_cv",
                               return_value=self.outcome(page_count=2, warnings=["w1"])) as run_cv:
            code, out, err = self.cli("--action", "cv", "--role", "Lead iOS Engineer", "--provider", "claudecode",
                                      "--theme", "default", "--steering-file", str(steering), "--out", str(out_path))
        self.assertEqual(code, 0)
        kwargs = run_cv.call_args.kwargs
        self.assertEqual(run_cv.call_args.args[1], self.role_id)
        self.assertEqual((kwargs["provider"], kwargs["theme"], kwargs["steering"], kwargs["make_current"]),
                         ("claudecode", "", "lead with accessibility", True))
        self.assertEqual(out_path.read_bytes(), b"%PDF-fake")
        self.assertIn("CV run 41 saved (2 page(s)), now current.", out)
        self.assertIn("warning: w1", err)

    def test_cv_defaults_and_no_steering(self) -> None:
        with mock.patch.object(role_runner, "run_cv", return_value=self.outcome()) as run_cv:
            self.cli("--action", "cv", "--role", "lead-ios-engineer")
            self.assertEqual((run_cv.call_args.kwargs["theme"], run_cv.call_args.kwargs["steering"]), (None, None))
            self.cli("--action", "cv", "--role", "lead-ios-engineer", "--no-steering", "--no-current")
            self.assertEqual(run_cv.call_args.kwargs["steering"], "")
            self.assertFalse(run_cv.call_args.kwargs["make_current"])

    def test_cv_failure_and_refusals(self) -> None:
        with mock.patch.object(role_runner, "run_cv", return_value=self.outcome(success=False)):
            code, _, err = self.cli("--action", "cv", "--role", "lead-ios-engineer")
        self.assertEqual(code, 1)
        self.assertIn("CV run 41 failed: boom", err)
        self.assertEqual(self.cli("--action", "cv", "--role", "nope")[0], 1)
        code, _, err = self.cli("--action", "cv", "--role", "lead-ios-engineer", "--theme", "bogus")
        self.assertEqual(code, 1)
        self.assertIn("unknown theme", err)

    def test_ctrl_c_stops_the_script_and_exits_130(self) -> None:
        proc = mock.Mock()
        proc.poll.return_value = None

        def interrupted(*args, **kwargs):
            kwargs["on_start"](proc)
            raise KeyboardInterrupt

        with mock.patch.object(role_runner, "run_cv", side_effect=interrupted):
            code, _, err = self.cli("--action", "cv", "--role", "lead-ios-engineer")
        self.assertEqual(code, 130)
        proc.terminate.assert_called_once()
        self.assertIn("wasn't saved", err)

    def test_research_passes_the_options(self) -> None:
        with mock.patch.object(role_runner, "run_research", return_value=self.outcome()) as run_research:
            code, out, _ = self.cli("--action", "research", "--role", "lead-ios-engineer", "--url", "https://a",
                                    "--url", "https://b", "--dry-run", "--company", "Other")
        self.assertEqual(code, 0)
        kwargs = run_research.call_args.kwargs
        self.assertEqual((kwargs["urls"], kwargs["dry_run"], kwargs["company"]),
                         (["https://a", "https://b"], True, "Other"))
        self.assertIn("Research run 41 saved", out)

    def test_render_refusals(self) -> None:
        store.create_role(self.conn, "Empty")
        store.seed_role_cv(self.conn, store.find_role(self.conn, "empty")["id"])
        code, _, err = self.cli("--action", "render", "--role", "empty")
        self.assertEqual(code, 1)
        self.assertIn("no current CV run", err)
        code, _, err = self.cli("--action", "render", "--role", "lead-ios-engineer", "--run", "999")
        self.assertIn("no CV run 999", err)
        code, _, err = self.cli("--action", "render", "--role", "empty", "--theme", "bogus")
        self.assertIn("unknown theme", err)

    @unittest.skipUnless(HAS_RENDERER, "pandoc and typst are needed to render")
    def test_render_current_run(self) -> None:
        out_path = self.tmp / "cv.pdf"
        code, out, _ = self.cli("--action", "render", "--role", "lead-ios-engineer", "--out", str(out_path))
        self.assertEqual(code, 0)
        self.assertTrue(out_path.read_bytes().startswith(b"%PDF"))
        self.assertIn(f"Wrote {out_path}", out)

    def research_run(self, **fields) -> int:
        fields = {"success": True, "output_md": "# Notes\n\nAcme ships apps.", **fields}
        return store.add_research_run(self.conn, self.role_id, **fields)

    def test_research_out_writes_the_runs_pdf(self) -> None:
        out_path = self.tmp / "out" / "research.pdf"
        run_id = self.research_run(make_current=False)
        outcome = role_runner.RunOutcome(run_id, True, None, "log")
        with mock.patch.object(role_runner, "run_research", return_value=outcome), \
                mock.patch.object(resumator, "render_research_pdf", return_value=b"%PDF-r") as render:
            code, out, _ = self.cli("--action", "research", "--role", "lead-ios-engineer", "--out", str(out_path))
        self.assertEqual(code, 0)
        self.assertEqual(render.call_args.args[0], "# Notes\n\nAcme ships apps.")
        self.assertEqual(out_path.read_bytes(), b"%PDF-r")

    def test_research_out_refuses_a_dry_run(self) -> None:
        run_id = self.research_run(output_md="", dry_run=True)
        outcome = role_runner.RunOutcome(run_id, True, None, "log")
        with mock.patch.object(role_runner, "run_research", return_value=outcome):
            code, _, err = self.cli("--action", "research", "--role", "lead-ios-engineer", "--dry-run",
                                    "--out", str(self.tmp / "r.pdf"))
        self.assertEqual(code, 1)
        self.assertIn(f"research run {run_id} has no output to render (dry run)", err)
        self.assertFalse((self.tmp / "r.pdf").exists())

    def test_render_research_current_and_given_run(self) -> None:
        old = self.research_run(output_md="old notes")
        self.research_run(output_md="current notes")
        current = store.current_research_run(self.conn, self.role_id)["id"]
        with mock.patch.object(resumator, "render_research_pdf", return_value=b"%PDF-r") as render, \
                mock.patch.object(resumator, "OUTPUT_DIR", self.tmp / "output"):
            code, out, _ = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer")
            self.assertEqual(code, 0)
            self.assertEqual(render.call_args.args[0], "current notes")
            self.assertIn(f"lead-ios-engineer-research{current}.pdf", out)
            out_path = self.tmp / "given.pdf"
            code, _, _ = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer",
                                  "--run", str(old), "--out", str(out_path))
        self.assertEqual(code, 0)
        self.assertEqual(render.call_args.args[0], "old notes")
        self.assertEqual(out_path.read_bytes(), b"%PDF-r")

    def test_render_research_refusals(self) -> None:
        code, _, err = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer")
        self.assertEqual(code, 1)
        self.assertIn("no current research run", err)
        failed = self.research_run(success=False, output_md="")
        code, _, err = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer",
                                "--run", str(failed))
        self.assertIn(f"research run {failed} has no output to render", err)
        cv_run = store.current_cv_run(self.conn, self.role_id)["id"]
        code, _, err = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer",
                                "--run", str(cv_run + 999))
        self.assertIn(f"no research run {cv_run + 999}", err)
        code, _, err = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer",
                                "--format", "docx")
        self.assertIn("PDF only", err)
        code, _, err = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer",
                                "--theme", "compact")
        self.assertIn("PDF only", err)
        with mock.patch.object(resumator, "render_research_pdf", side_effect=RuntimeError("pandoc died")):
            self.research_run()
            code, _, err = self.cli("--action", "render", "--kind", "research", "--role", "lead-ios-engineer",
                                    "--out", str(self.tmp / "x.pdf"))
        self.assertEqual(code, 1)
        self.assertIn("failed: pandoc died", err)


class MigrateTests(CliTestCase):
    def test_migrate_passes_through(self) -> None:
        with mock.patch.object(resumator.migrate_single_role, "main", return_value=0) as main:
            code, _, _ = self.cli("--action", "migrate-single-role", "--role", "Quantum Base", "--archive", "a",
                                  "--no-research")
        self.assertEqual(code, 0)
        self.assertEqual(main.call_args.args[0],
                         ["--name", "Quantum Base", "--db", str(self.db), "--archive", "a", "--no-research"])


if __name__ == "__main__":
    unittest.main()
