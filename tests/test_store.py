import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cv_web import store
from cv_web.store import StoreError


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.conn = store.connect(self.db_path)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def make_role_with_cv(self, name: str = "Quantum Base") -> tuple[int, int, int]:
        """Master v1 + a seeded role. Returns (master_id, role_id, role_cv_id)."""
        master_id = store.add_cv_version(self.conn, "# Candidate\nName: Ada\n", source="import")
        role_id = store.create_role(self.conn, name, company="QB", jobspec="Lead Mobile Engineer")
        role_cv_id = store.seed_role_cv(self.conn, role_id)
        return master_id, role_id, role_cv_id


class MigrationTests(StoreTestCase):
    def test_new_db_is_migrated_with_foreign_keys_and_wal(self) -> None:
        self.assertEqual(store.schema_version(self.conn), len(store.MIGRATIONS))
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue(
            {"role", "cv_version", "prompt_version", "cv_run", "research_run", "setting", "schema_version"} <= tables
        )
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_migrate_is_idempotent(self) -> None:
        self.conn.close()
        self.conn = store.connect(self.db_path)
        self.assertEqual(store.migrate(self.conn), len(store.MIGRATIONS))
        count = self.conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        self.assertEqual(count, len(store.MIGRATIONS))

    def test_new_migration_applies_on_reconnect(self) -> None:
        self.conn.close()
        extra = store.MIGRATIONS + ("CREATE TABLE extra (id INTEGER PRIMARY KEY);",)
        with mock.patch.object(store, "MIGRATIONS", extra):
            self.conn = store.connect(self.db_path)
            self.assertEqual(store.schema_version(self.conn), len(extra))

    def test_failed_migration_rolls_back(self) -> None:
        self.conn.close()
        broken = store.MIGRATIONS + ("CREATE TABLE half (id INTEGER);\nCREATE TABLE role (id INTEGER);",)
        with mock.patch.object(store, "MIGRATIONS", broken):
            with self.assertRaises(sqlite3.OperationalError):
                store.connect(self.db_path)
        self.conn = store.connect(self.db_path)
        self.assertEqual(store.schema_version(self.conn), len(store.MIGRATIONS))
        self.assertIsNone(
            self.conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'half'").fetchone()
        )

    def test_newer_db_than_code_is_refused(self) -> None:
        self.conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (999, 'x')")
        with self.assertRaises(StoreError):
            store.migrate(self.conn)

    def test_memory_db(self) -> None:
        conn = store.connect(":memory:")
        try:
            self.assertEqual(store.schema_version(conn), len(store.MIGRATIONS))
        finally:
            conn.close()


class RoleTests(StoreTestCase):
    def test_create_and_get(self) -> None:
        role_id = store.create_role(self.conn, "  Quantum Base  ", company="QB", jobspec="spec")
        role = store.get_role(self.conn, role_id)
        self.assertEqual(role["name"], "Quantum Base")
        self.assertEqual(role["slug"], "quantum-base")
        self.assertEqual(role["status"], "draft")
        self.assertEqual(role["steering_enabled"], 1)
        self.assertEqual(role["created_at"], role["updated_at"])
        self.assertEqual(store.get_role_by_slug(self.conn, "quantum-base")["id"], role_id)

    def test_slug_is_made_unique(self) -> None:
        first = store.create_role(self.conn, "Quantum Base")
        second = store.create_role(self.conn, "Quantum  base!")
        third = store.create_role(self.conn, "Quantum Base")
        slugs = [store.get_role(self.conn, rid)["slug"] for rid in (first, second, third)]
        self.assertEqual(slugs, ["quantum-base", "quantum-base-2", "quantum-base-3"])
        self.assertEqual(store.slugify("!!!"), "role")

    def test_find_role_by_slug_or_name(self) -> None:
        role_id = store.create_role(self.conn, "Quantum Base")
        for query in ("quantum-base", "Quantum Base", "QUANTUM BASE"):
            self.assertEqual(store.find_role(self.conn, query)["id"], role_id)
        self.assertIsNone(store.find_role(self.conn, "Nope"))

    def test_invalid_role_values_are_refused(self) -> None:
        with self.assertRaises(StoreError):
            store.create_role(self.conn, "   ")
        with self.assertRaises(StoreError):
            store.create_role(self.conn, "X", status="hired")
        role_id = store.create_role(self.conn, "X")
        with self.assertRaises(StoreError):
            store.update_role(self.conn, role_id, status="hired")
        with self.assertRaises(StoreError):
            store.update_role(self.conn, role_id, id=5)
        with self.assertRaises(StoreError):
            store.update_role(self.conn, role_id, name=" ")
        with self.assertRaises(StoreError):
            store.update_role(self.conn, 999, name="Y")

    def test_update_role(self) -> None:
        role_id = store.create_role(self.conn, "Quantum Base")
        other = store.create_role(self.conn, "Other")
        with mock.patch.object(store, "now_iso", return_value="2099-01-01T00:00:00Z"):
            role = store.update_role(
                self.conn, role_id, status="applied", steering_enabled=False, theme="compact", slug="Other"
            )
        self.assertEqual(role["status"], "applied")
        self.assertEqual(role["steering_enabled"], 0)
        self.assertEqual(role["theme"], "compact")
        self.assertEqual(role["slug"], "other-2")
        self.assertEqual(role["updated_at"], "2099-01-01T00:00:00Z")
        # Keeping its own slug doesn't add a suffix.
        self.assertEqual(store.update_role(self.conn, other, slug="other")["slug"], "other")

    def test_list_roles_order_filter_and_run_summary(self) -> None:
        _, role_id, cv_id = self.make_role_with_cv("First")
        second = store.create_role(self.conn, "Second", status="applied")
        self.conn.execute("UPDATE role SET updated_at = '2000-01-01T00:00:00Z' WHERE id = ?", (second,))
        store.add_cv_run(self.conn, role_id, cv_id, success=True, steering_text="lead with RN",
                         started_at="2026-10-21T10:00:00Z")
        store.add_research_run(self.conn, role_id, success=True, started_at="2026-10-21T11:00:00Z")

        roles = store.list_roles(self.conn)
        self.assertEqual([r["name"] for r in roles], ["First", "Second"])
        self.assertEqual(roles[0]["last_run_at"], "2026-10-21T11:00:00Z")
        self.assertEqual(roles[0]["current_steered"], 1)
        self.assertIsNone(roles[1]["last_run_at"])
        self.assertIsNone(roles[1]["current_steered"])
        self.assertEqual([r["name"] for r in store.list_roles(self.conn, status="applied")], ["Second"])
        with self.assertRaises(StoreError):
            store.list_roles(self.conn, status="nope")

    def test_delete_role_cascades_but_keeps_master(self) -> None:
        master_id, role_id, cv_id = self.make_role_with_cv()
        store.add_cv_version(self.conn, "edited", source="edit", role_id=role_id)
        store.add_cv_run(self.conn, role_id, cv_id, success=True)
        store.add_research_run(self.conn, role_id, success=False)

        self.assertTrue(store.delete_role(self.conn, role_id))
        self.assertFalse(store.delete_role(self.conn, role_id))
        for table in ("cv_run", "research_run"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual([v["id"] for v in store.list_cv_versions(self.conn)], [master_id])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cv_version").fetchone()[0], 1)


class CvVersionTests(StoreTestCase):
    def test_master_versions_chain_by_parent(self) -> None:
        v1 = store.add_cv_version(self.conn, "one", source="import")
        v2 = store.add_cv_version(self.conn, "two", source="edit", note="typo")
        self.assertIsNone(store.get_cv_version(self.conn, v1)["parent_id"])
        self.assertEqual(store.get_cv_version(self.conn, v2)["parent_id"], v1)
        self.assertEqual(store.current_cv_version(self.conn)["content"], "two")
        history = store.list_cv_versions(self.conn)
        self.assertEqual([v["id"] for v in history], [v2, v1])
        self.assertNotIn("content", history[0])
        self.assertEqual(store.list_cv_versions(self.conn, include_content=True)[1]["content"], "one")

    def test_seed_copies_master_and_records_base(self) -> None:
        master_id, role_id, role_cv_id = self.make_role_with_cv()
        seeded = store.get_cv_version(self.conn, role_cv_id)
        self.assertEqual(seeded["role_id"], role_id)
        self.assertEqual(seeded["source"], "seed")
        self.assertEqual(seeded["base_master_id"], master_id)
        self.assertIsNone(seeded["parent_id"])
        self.assertEqual(seeded["content"], store.get_cv_version(self.conn, master_id)["content"])

    def test_role_edits_inherit_base_and_dont_touch_master(self) -> None:
        master_id, role_id, role_cv_id = self.make_role_with_cv()
        edit_id = store.add_cv_version(self.conn, "role edit", source="edit", role_id=role_id)
        edit = store.get_cv_version(self.conn, edit_id)
        self.assertEqual(edit["parent_id"], role_cv_id)
        self.assertEqual(edit["base_master_id"], master_id)
        self.assertEqual(store.current_cv_version(self.conn, role_id)["content"], "role edit")
        self.assertEqual(store.current_cv_version(self.conn)["id"], master_id)

    def test_pull_moves_base_forward(self) -> None:
        _, role_id, _ = self.make_role_with_cv()
        master_v2 = store.add_cv_version(self.conn, "master two", source="edit")
        pulled = store.add_cv_version(self.conn, "merged", source="pull", role_id=role_id, base_master_id=master_v2)
        self.assertEqual(store.get_cv_version(self.conn, pulled)["base_master_id"], master_v2)

    def test_version_rules(self) -> None:
        master_id, role_id, role_cv_id = self.make_role_with_cv()
        bare_role = store.create_role(self.conn, "Bare")
        cases = [
            dict(content="x", source="bogus"),
            dict(content="x", source="edit", base_master_id=master_id),  # master with a base
            dict(content="x", source="edit", role_id=bare_role),  # role's first version without a base
            dict(content="x", source="pull", role_id=role_id, base_master_id=role_cv_id),  # base not master
            dict(content="x", source="pull", role_id=role_id, base_master_id=999),
            dict(content="x", source="edit", role_id=999, base_master_id=master_id),
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(StoreError):
                store.add_cv_version(self.conn, **kwargs)

    def test_schema_check_rejects_master_with_base(self) -> None:
        master_id = store.add_cv_version(self.conn, "m", source="import")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO cv_version (role_id, base_master_id, source, content, created_at) "
                "VALUES (NULL, ?, 'edit', 'x', 'now')",
                (master_id,),
            )

    def test_seed_without_master_is_refused(self) -> None:
        role_id = store.create_role(self.conn, "X")
        with self.assertRaises(StoreError):
            store.seed_role_cv(self.conn, role_id)

    def test_role_cv_change_bumps_role_updated_at(self) -> None:
        _, role_id, _ = self.make_role_with_cv()
        with mock.patch.object(store, "now_iso", return_value="2099-01-01T00:00:00Z"):
            store.add_cv_version(self.conn, "edit", source="edit", role_id=role_id)
        self.assertEqual(store.get_role(self.conn, role_id)["updated_at"], "2099-01-01T00:00:00Z")


class PromptTests(StoreTestCase):
    def test_prompts_are_deduplicated_by_hash(self) -> None:
        first = store.save_prompt(self.conn, "cv", "prompt text")
        again = store.save_prompt(self.conn, "cv", "prompt text")
        other = store.save_prompt(self.conn, "research", "other text")
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertEqual(first, store.prompt_hash("prompt text"))
        self.assertEqual(store.get_prompt(self.conn, first)["content"], "prompt text")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prompt_version").fetchone()[0], 2)
        with self.assertRaises(StoreError):
            store.save_prompt(self.conn, "other", "x")


class RunTests(StoreTestCase):
    def test_cv_run_round_trips_json_and_becomes_current(self) -> None:
        _, role_id, cv_id = self.make_role_with_cv()
        digest = store.save_prompt(self.conn, "cv", "p")
        model_json = {"profile": "Ada", "metadata": {"page_count": 2, "steering": "lead with RN"}}
        run_id = store.add_cv_run(
            self.conn, role_id, cv_id, success=True, provider="gemini", model="gemini-2.5-flash",
            theme="compact", steering_text="lead with RN", prompt_hash=digest, raw_output="```json…",
            model_json=model_json, warnings_json=["too long"], page_count=2, log="line 1\n",
            started_at="2026-10-21T10:00:00Z", finished_at="2026-10-21T10:01:00Z",
        )
        run = store.get_cv_run(self.conn, run_id)
        self.assertEqual(run["model_json"], model_json)
        self.assertEqual(run["warnings_json"], ["too long"])
        self.assertEqual(run["is_current"], 1)
        self.assertEqual(store.current_cv_run(self.conn, role_id)["id"], run_id)
        # The JSON is queryable in SQL (spike finding).
        pages = self.conn.execute(
            "SELECT json_extract(model_json, '$.metadata.page_count') FROM cv_run WHERE id = ?", (run_id,)
        ).fetchone()[0]
        self.assertEqual(pages, 2)

    def test_one_current_run_per_role_and_failed_runs_never_current(self) -> None:
        _, role_id, cv_id = self.make_role_with_cv()
        first = store.add_cv_run(self.conn, role_id, cv_id, success=True)
        second = store.add_cv_run(self.conn, role_id, cv_id, success=True)
        failed = store.add_cv_run(self.conn, role_id, cv_id, success=False, log="boom")
        kept = store.add_cv_run(self.conn, role_id, cv_id, success=True, make_current=False)
        self.assertEqual(store.current_cv_run(self.conn, role_id)["id"], second)
        self.assertEqual(store.get_cv_run(self.conn, failed)["is_current"], 0)

        store.set_current_cv_run(self.conn, first)
        self.assertEqual(store.current_cv_run(self.conn, role_id)["id"], first)
        with self.assertRaises(StoreError):
            store.set_current_cv_run(self.conn, failed)
        with self.assertRaises(StoreError):
            store.set_current_cv_run(self.conn, 999)
        self.assertEqual(store.current_cv_run(self.conn, role_id)["id"], first)

        history = store.list_cv_runs(self.conn, role_id)
        self.assertEqual([r["id"] for r in history], [kept, failed, second, first])
        self.assertNotIn("raw_output", history[0])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE cv_run SET is_current = 1 WHERE id = ?", (second,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE cv_run SET is_current = 1 WHERE id = ?", (failed,))

    def test_current_runs_are_per_role(self) -> None:
        _, role_a, cv_a = self.make_role_with_cv("A")
        role_b = store.create_role(self.conn, "B")
        cv_b = store.seed_role_cv(self.conn, role_b)
        run_a = store.add_cv_run(self.conn, role_a, cv_a, success=True)
        run_b = store.add_cv_run(self.conn, role_b, cv_b, success=True)
        self.assertEqual(store.current_cv_run(self.conn, role_a)["id"], run_a)
        self.assertEqual(store.current_cv_run(self.conn, role_b)["id"], run_b)

    def test_cv_run_must_use_the_roles_own_cv(self) -> None:
        master_id, role_id, _ = self.make_role_with_cv("A")
        other = store.create_role(self.conn, "B")
        other_cv = store.seed_role_cv(self.conn, other)
        for cv_id in (master_id, other_cv, 999):
            with self.subTest(cv_id=cv_id), self.assertRaises(StoreError):
                store.add_cv_run(self.conn, role_id, cv_id, success=True)
        with self.assertRaises(StoreError):
            store.add_cv_run(self.conn, role_id, store.current_cv_version(self.conn, role_id)["id"],
                             success=True, bogus=1)

    def test_invalid_json_text_is_rejected_by_schema(self) -> None:
        _, role_id, cv_id = self.make_role_with_cv()
        run_id = store.add_cv_run(self.conn, role_id, cv_id, success=True)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE cv_run SET model_json = '{not json' WHERE id = ?", (run_id,))

    def test_research_runs(self) -> None:
        _, role_id, _ = self.make_role_with_cv()
        first = store.add_research_run(
            self.conn, role_id, success=True, company="Quantum Base", urls_json=["https://qb.example"],
            dry_run=0, output_json={"summary": "s"}, output_md="# QB",
        )
        dry = store.add_research_run(self.conn, role_id, success=True, dry_run=True, make_current=False)
        run = store.get_research_run(self.conn, first)
        self.assertEqual(run["urls_json"], ["https://qb.example"])
        self.assertEqual(run["output_json"], {"summary": "s"})
        self.assertEqual(store.get_research_run(self.conn, dry)["dry_run"], 1)
        self.assertEqual(store.current_research_run(self.conn, role_id)["id"], first)
        store.set_current_research_run(self.conn, dry)
        self.assertEqual(store.current_research_run(self.conn, role_id)["id"], dry)
        self.assertEqual([r["id"] for r in store.list_research_runs(self.conn, role_id)], [dry, first])
        with self.assertRaises(StoreError):
            store.add_research_run(self.conn, 999, success=True)
        with self.assertRaises(StoreError):
            store.add_research_run(self.conn, role_id, success=True, cv_version_id=1)


class TransactionTests(StoreTestCase):
    def test_error_rolls_back_whole_block(self) -> None:
        with self.assertRaises(RuntimeError):
            with store.transaction(self.conn):
                store.create_role(self.conn, "Gone")
                raise RuntimeError("abort")
        self.assertEqual(store.list_roles(self.conn), [])
        self.assertFalse(self.conn.in_transaction)


class SettingTests(StoreTestCase):
    def test_settings(self) -> None:
        self.assertEqual(store.get_setting(self.conn, "first_run_done", "0"), "0")
        store.set_setting(self.conn, "first_run_done", "1")
        store.set_setting(self.conn, "first_run_done", "2")
        self.assertEqual(store.get_setting(self.conn, "first_run_done"), "2")
        store.delete_setting(self.conn, "first_run_done")
        self.assertIsNone(store.get_setting(self.conn, "first_run_done"))


class BackupTests(StoreTestCase):
    def test_backup_writes_a_readable_timestamped_copy(self) -> None:
        self.make_role_with_cv()
        dest_dir = Path(self.tmp.name) / "backups"
        first = store.backup(self.conn, dest_dir)
        second = store.backup(self.conn, dest_dir)
        self.assertNotEqual(first, second)
        self.assertRegex(first.name, r"^resumator-\d{8}-\d{6}(-\d+)?\.db$")
        copy = sqlite3.connect(str(first))
        try:
            self.assertEqual(copy.execute("SELECT name FROM role").fetchone()[0], "Quantum Base")
        finally:
            copy.close()


if __name__ == "__main__":
    unittest.main()
