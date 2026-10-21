"""Tests for cv_web/first_run.py: the first-run choice (example data or blank) on a temp DB, and the shipped
examples/ files."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv_source  # noqa: E402
from cv_web import first_run, server_roles, store  # noqa: E402


class FirstRunTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.conn = store.connect(self.tmp / "test.db")
        self.addCleanup(self.conn.close)


class StatusTests(FirstRunTestCase):
    def test_empty_db_needs_the_choice(self) -> None:
        self.assertEqual(first_run.status(self.conn),
                         {"needed": True, "done": None, "hasMaster": False, "roleCount": 0})

    def test_a_migrated_install_never_needs_it(self) -> None:
        store.add_cv_version(self.conn, "# Candidate\n", source="import")
        self.assertFalse(first_run.status(self.conn)["needed"])

    def test_not_needed_once_done_even_if_emptied(self) -> None:
        first_run.set_up(self.conn, "example")
        role_id = store.list_roles(self.conn)[0]["id"]
        store.delete_role(self.conn, role_id)
        self.conn.execute("DELETE FROM cv_version")
        status = first_run.status(self.conn)
        self.assertEqual((status["needed"], status["done"]), (False, "example"))


class SetUpTests(FirstRunTestCase):
    def test_example_creates_master_role_and_current_run(self) -> None:
        result = first_run.set_up(self.conn, "example")
        master = store.current_cv_version(self.conn, None)
        self.assertEqual((master["id"], master["source"]), (result["masterVersionId"], "example"))
        role = store.get_role(self.conn, result["roleId"])
        self.assertEqual((role["name"], role["company"]), ("Lead iOS Engineer", "Northwind Health"))
        self.assertIn("Lead iOS Engineer", role["jobspec"])
        role_cv = store.current_cv_version(self.conn, role["id"])
        self.assertEqual((role_cv["source"], role_cv["base_master_id"], role_cv["content"]),
                         ("seed", master["id"], master["content"]))
        run = store.current_cv_run(self.conn, role["id"])
        self.assertEqual((run["id"], run["cv_version_id"], run["success"]), (result["runId"], role_cv["id"], 1))
        self.assertEqual(run["model_json"]["metadata"]["company"], "Northwind Health")
        self.assertEqual(run["warnings_json"], [])
        self.assertEqual(store.get_setting(self.conn, "first_run_done"), "example")

    def test_example_run_renders_tagged_markdown(self) -> None:
        result = first_run.set_up(self.conn, "example")
        markdown = server_roles.run_markdown(self.conn, store.get_cv_run(self.conn, result["runId"]))
        self.assertIn("Alex Morgan", markdown)
        self.assertIn("Brightwater Bank", markdown)

    def test_blank_creates_only_the_template_master(self) -> None:
        result = first_run.set_up(self.conn, "blank")
        self.assertEqual((result["roleId"], result["runId"]), (None, None))
        master = store.current_cv_version(self.conn, None)
        self.assertEqual((master["source"], master["note"]), ("example", "Blank master CV template"))
        self.assertIn("Name: TODO", master["content"])
        self.assertEqual(store.list_roles(self.conn), [])
        self.assertEqual(store.get_setting(self.conn, "first_run_done"), "blank")

    def test_refusals(self) -> None:
        with self.assertRaises(first_run.FirstRunError) as caught:
            first_run.set_up(self.conn, "import")
        self.assertEqual(caught.exception.status, 400)
        first_run.set_up(self.conn, "blank")
        with self.assertRaises(first_run.FirstRunError) as caught:
            first_run.set_up(self.conn, "example")
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(store.list_roles(self.conn), [])

    def test_missing_files_change_nothing(self) -> None:
        examples = self.tmp / "examples"
        shutil.copytree(first_run.EXAMPLES_DIR, examples)
        (examples / "run.json").unlink()
        with self.assertRaises(first_run.FirstRunError) as caught:
            first_run.set_up(self.conn, "example", examples)
        self.assertEqual(caught.exception.status, 500)
        self.assertTrue(first_run.status(self.conn)["needed"])

    def test_a_bad_canned_run_rolls_back(self) -> None:
        examples = self.tmp / "examples"
        shutil.copytree(first_run.EXAMPLES_DIR, examples)
        (examples / "run.json").write_text('{"startedAt": "2026-10-01T09:00:00+00:00", "output": {}}')
        with self.assertRaises(ValueError):
            first_run.set_up(self.conn, "example", examples)
        self.assertTrue(first_run.status(self.conn)["needed"])


class ExampleFileTests(unittest.TestCase):
    def test_example_cvs_lint_without_errors(self) -> None:
        for name in ("master-cv.md", "blank-cv.md"):
            with self.subTest(name=name):
                text = (first_run.EXAMPLES_DIR / name).read_text(encoding="utf-8")
                issues = cv_source.lint_cv_source(cv_source.parse_cv_source(text))
                self.assertEqual([issue for issue in issues if issue["level"] == "error"], [])


if __name__ == "__main__":
    unittest.main()
