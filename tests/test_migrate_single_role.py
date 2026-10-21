"""Tests for cv_web/migrate_single_role.py: today's input/ and output/ files → master CV, one role and its runs (R4).

Fixture files are written to a temp folder; the real `input/` and `output/` are never read.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
for path in (ROOT_DIR, ROOT_DIR / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cv_web import migrate_single_role as migration, store  # noqa: E402
from cv_web.migrate_single_role import MigrationError, migrate_single_role  # noqa: E402
from test_cv_source import MINIMAL  # noqa: E402
from test_generate_cv import valid_payload  # noqa: E402


def write_cv_run(run_dir: Path, *, steering: str | None, mtime: int, company: str = "Engine Co") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = valid_payload()
    metadata = {"company": company, "page_count": 3, "warnings": ["the PDF has 3 pages; the target is 2"]}
    if steering:
        metadata["steering"] = steering
    payload["metadata"] = metadata
    (run_dir / "tailored.model-output.txt").write_text("raw " + json.dumps(payload), encoding="utf-8")
    (run_dir / "tailored.model.json").write_text(json.dumps(payload), encoding="utf-8")
    for name in ("tailored.model-output.txt", "tailored.model.json"):
        os.utime(run_dir / name, (mtime, mtime))


class MigrateSingleRoleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.db_path = self.tmp / "test.db"
        self.conn = store.connect(self.db_path)
        self.addCleanup(self.conn.close)
        self.input_dir = self.tmp / "input"
        self.output_dir = self.tmp / "output"
        self.input_dir.mkdir()
        (self.input_dir / "CV.md").write_text(MINIMAL, encoding="utf-8")
        (self.input_dir / "jobspec.txt").write_text("Senior Analyst at Engine Co.", encoding="utf-8")
        (self.input_dir / "research_company.txt").write_text("Engine Co\n", encoding="utf-8")
        (self.input_dir / "research_urls.txt").write_text("https://engine.example\n", encoding="utf-8")
        write_cv_run(self.output_dir, steering="lead with maths", mtime=1_800_000_300)
        write_cv_run(self.tmp / "old-b", steering=None, mtime=1_800_000_200)
        write_cv_run(self.tmp / "old-a", steering=None, mtime=1_800_000_100)
        envelope = {"companyName": "Engine Co", "provider": "claudecode", "model": "opus",
                    "urls": ["https://engine.example"], "dryRun": False, "output": "notes"}
        (self.output_dir / "research_output.json").write_text(json.dumps(envelope), encoding="utf-8")
        (self.output_dir / "research_output.md").write_text("# Engine Co\n\nnotes\n", encoding="utf-8")

    def migrate(self, **kwargs):
        kwargs.setdefault("input_dir", self.input_dir)
        kwargs.setdefault("output_dir", self.output_dir)
        return migrate_single_role(self.conn, "Engine Co Analyst", **kwargs)

    def test_imports_master_role_and_runs(self) -> None:
        report = self.migrate(archive_dirs=(self.tmp / "old-b", self.tmp / "old-a"))

        master = store.current_cv_version(self.conn, None)
        self.assertEqual((master["id"], master["source"], master["content"]),
                         (report.master_version_id, "import", MINIMAL))
        role = store.get_role(self.conn, report.role_id)
        self.assertEqual((role["name"], role["company"], role["jobspec"], role["status"]),
                         ("Engine Co Analyst", "Engine Co", "Senior Analyst at Engine Co.", "draft"))
        cv = store.current_cv_version(self.conn, report.role_id)
        self.assertEqual((cv["id"], cv["source"], cv["base_master_id"], cv["content"]),
                         (report.cv_version_id, "seed", master["id"], MINIMAL))

        runs = sorted(store.list_cv_runs(self.conn, report.role_id), key=lambda run: run["id"])
        self.assertEqual([run["id"] for run in runs], report.cv_run_ids)
        self.assertEqual([run["started_at"] for run in runs],
                         ["2027-01-15T08:01:40Z", "2027-01-15T08:03:20Z", "2027-01-15T08:05:00Z"])
        current = store.current_cv_run(self.conn, report.role_id)
        self.assertEqual(current["id"], report.current_cv_run_id)
        self.assertEqual(current["id"], report.cv_run_ids[-1])
        self.assertEqual(current["steering_text"], "lead with maths")
        self.assertEqual((current["page_count"], current["warnings_json"]),
                         (3, ["the PDF has 3 pages; the target is 2"]))
        self.assertEqual(current["model_json"]["metadata"]["company"], "Engine Co")
        self.assertTrue(current["raw_output"].startswith("raw {"))
        self.assertIsNone(current["prompt_hash"])
        self.assertIsNone(current["provider"])
        self.assertIn("[migrate] imported from", current["log"])
        self.assertIsNone(store.get_cv_run(self.conn, report.cv_run_ids[0])["steering_text"])

        research = store.current_research_run(self.conn, report.role_id)
        self.assertEqual(research["id"], report.research_run_id)
        self.assertEqual((research["company"], research["urls_json"], research["provider"], research["dry_run"]),
                         ("Engine Co", ["https://engine.example"], "claudecode", 0))
        self.assertEqual(research["output_json"]["output"], "notes")
        self.assertEqual(research["output_md"], "# Engine Co\n\nnotes\n")

    def test_second_run_skips_and_writes_nothing(self) -> None:
        first = self.migrate()
        counts = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM cv_version), (SELECT COUNT(*) FROM cv_run), (SELECT COUNT(*) FROM role)"
        ).fetchone()
        second = self.migrate()
        self.assertTrue(second.skipped)
        self.assertEqual(second.role_id, first.role_id)
        self.assertEqual(tuple(counts), tuple(self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM cv_version), (SELECT COUNT(*) FROM cv_run), (SELECT COUNT(*) FROM role)"
        ).fetchone()))

    def test_existing_identical_master_is_reused(self) -> None:
        master_id = store.add_cv_version(self.conn, MINIMAL, source="import")
        report = self.migrate()
        self.assertFalse(report.master_imported)
        self.assertEqual(report.master_version_id, master_id)
        self.assertEqual(len(store.list_cv_versions(self.conn, None)), 1)

    def test_changed_master_gets_a_new_import_version(self) -> None:
        old_id = store.add_cv_version(self.conn, MINIMAL + "\n<!-- older -->\n", source="import")
        report = self.migrate()
        self.assertTrue(report.master_imported)
        self.assertEqual(store.get_cv_version(self.conn, report.master_version_id)["parent_id"], old_id)

    def test_research_fallbacks_and_opt_out(self) -> None:
        (self.output_dir / "research_output.json").write_text(json.dumps({"output": "x"}), encoding="utf-8")
        (self.output_dir / "research_output.md").unlink()
        report = self.migrate()
        research = store.get_research_run(self.conn, report.research_run_id)
        self.assertEqual((research["company"], research["urls_json"], research["output_md"]),
                         ("Engine Co", ["https://engine.example"], ""))

        store.delete_role(self.conn, report.role_id)
        self.assertIsNone(self.migrate(research=False).research_run_id)

    def test_missing_outputs_give_a_role_with_no_runs(self) -> None:
        empty_output = self.tmp / "empty"
        empty_output.mkdir()
        report = self.migrate(output_dir=empty_output, company="Given Co")
        self.assertEqual(report.cv_run_ids, [])
        self.assertIsNone(report.research_run_id)
        self.assertEqual(store.get_role(self.conn, report.role_id)["company"], "Given Co")

    def test_bad_files_write_nothing(self) -> None:
        cases = {
            "no CV": lambda: (self.input_dir / "CV.md").unlink(),
            "bad run JSON": lambda: (self.output_dir / "tailored.model.json").write_text("{", encoding="utf-8"),
            "archive without files": lambda: (self.tmp / "old-a" / "tailored.model-output.txt").unlink(),
        }
        for label, break_it in cases.items():
            with self.subTest(label):
                self.setUp()
                break_it()
                with self.assertRaises(MigrationError):
                    self.migrate(archive_dirs=(self.tmp / "old-a",))
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cv_version").fetchone()[0], 0)
                self.assertEqual(store.list_roles(self.conn), [])

    def test_main_from_cwd(self) -> None:
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        args = ["--name", "Engine Co Analyst", "--archive", "old-a", "--db", str(self.db_path)]
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(migration.main(args), 0)
        self.assertIn("Role 'Engine Co Analyst'", out.getvalue())
        with redirect_stdout(io.StringIO()) as again:
            self.assertEqual(migration.main(args), 0)
        self.assertIn("already exists", again.getvalue())

        (self.tmp / "input" / "CV.md").unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(migration.main(["--name", "Other", "--db", str(self.db_path)]), 1)
        self.assertIn("nothing written", err.getvalue())


if __name__ == "__main__":
    unittest.main()
