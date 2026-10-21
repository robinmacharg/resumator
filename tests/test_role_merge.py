"""Tests for cv_web/role_merge.py: promote and pull over a temp DB (multi-role step 10)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv_merge  # noqa: E402
from cv_web import role_merge, store  # noqa: E402

HEAD = "# Candidate\nName: Ada Lovelace\n\n# Roles\n"
ANALYST = "## Analyst | Engine Co\nDates: Jan 2020 - Present\n\n- Wrote the first program."
TUTOR = "## Tutor | Home\nDates: 2018 - 2019\n\n- Taught maths."
CLERK = "## Clerk | Office\nDates: 2016 - 2017\n\n- Filed things."

ANALYST_KEY = ("roles", "analyst | engine co")
TUTOR_KEY = ("roles", "tutor | home")
CLERK_KEY = ("roles", "clerk | office")


def cv(*entries: str) -> str:
    return HEAD + "\n" + "\n\n".join(entries) + "\n"


class RoleMergeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = store.connect(Path(tmp.name) / "test.db")
        self.addCleanup(self.conn.close)
        self.master_v1 = store.add_cv_version(self.conn, cv(ANALYST, TUTOR), source="import")
        self.role_id = store.create_role(self.conn, "Role")
        store.seed_role_cv(self.conn, self.role_id)

    def edit_role(self, content: str) -> int:
        return store.add_cv_version(self.conn, content, source="edit", role_id=self.role_id)

    def edit_master(self, content: str) -> int:
        return store.add_cv_version(self.conn, content, source="edit")

    def role_cv(self) -> dict:
        return store.current_cv_version(self.conn, self.role_id)

    def master_cv(self) -> dict:
        return store.current_cv_version(self.conn, None)

    def save(self, direction: str, accept=None, resolutions=None, **ids):
        current = role_merge.view(self.conn, self.role_id, direction)
        if accept is None:
            accept = {tuple(change["key"]) for change in current["changes"] if change["accept"]}
        return role_merge.apply(
            self.conn, self.role_id, direction,
            target_id=ids.get("target_id", current["targetId"]), source_id=ids.get("source_id", current["sourceId"]),
            accept=set(accept), resolutions=resolutions or {},
        )


class ViewTests(RoleMergeTestCase):
    def test_fresh_role_has_nothing_to_merge(self) -> None:
        for direction in role_merge.DIRECTIONS:
            body = role_merge.view(self.conn, self.role_id, direction)
            self.assertEqual(body["changes"], [])
            self.assertFalse(body["baseBehind"])
            self.assertEqual(body["baseId"], self.master_v1)

    def test_promote_view_lists_role_changes_with_removals_unticked(self) -> None:
        self.edit_role(cv(ANALYST + "\n- Also debugged it.", CLERK))
        body = role_merge.view(self.conn, self.role_id, role_merge.PROMOTE)
        self.assertEqual((body["targetId"], body["sourceId"]), (self.master_v1, self.role_cv()["id"]))
        by_key = {tuple(change["key"]): change for change in body["changes"]}
        self.assertEqual(
            {key: (change["status"], change["accept"]) for key, change in by_key.items()},
            {ANALYST_KEY: ("changed", True), TUTOR_KEY: ("removed", False), CLERK_KEY: ("added", True)},
        )
        self.assertIn("+- Also debugged it.", by_key[ANALYST_KEY]["diff"])
        self.assertEqual(by_key[TUTOR_KEY]["current"], TUTOR)
        self.assertIsNone(by_key[TUTOR_KEY]["incoming"])

    def test_refusals(self) -> None:
        with self.assertRaises(role_merge.MergeError):
            role_merge.view(self.conn, self.role_id, "sideways")
        empty = store.create_role(self.conn, "Empty")
        with self.assertRaises(role_merge.MergeError) as raised:
            role_merge.view(self.conn, empty, role_merge.PULL)
        self.assertEqual(raised.exception.status, 409)


class PromoteTests(RoleMergeTestCase):
    def test_promote_keeps_master_facts_the_role_removed(self) -> None:
        self.edit_role(cv(ANALYST, CLERK))  # removed Tutor, added Clerk
        result = self.save(role_merge.PROMOTE)
        master = self.master_cv()
        self.assertEqual((result["versionId"], master["source"]), (master["id"], "promote"))
        self.assertEqual(master["content"], cv(ANALYST, CLERK, TUTOR))  # an addition follows its predecessor
        # The role had every master change, so its base moves on and nothing is left to promote but the removal.
        self.assertTrue(result["baseMoved"])
        self.assertEqual((self.role_cv()["base_master_id"], self.role_cv()["source"]), (master["id"], "promote"))
        statuses = [change["status"] for change in role_merge.view(self.conn, self.role_id, "promote")["changes"]]
        self.assertEqual(statuses, ["removed"])
        self.assertEqual(role_merge.view(self.conn, self.role_id, "pull")["changes"], [])

    def test_promote_leaves_the_base_while_master_changes_are_unpulled(self) -> None:
        self.edit_master(cv(ANALYST, TUTOR + "\n- And physics."))
        self.edit_role(cv(ANALYST, TUTOR, CLERK))
        result = self.save(role_merge.PROMOTE)
        self.assertFalse(result["baseMoved"])
        self.assertEqual(self.master_cv()["content"], cv(ANALYST, TUTOR + "\n- And physics.", CLERK))
        self.assertEqual(self.role_cv()["base_master_id"], self.master_v1)
        # Pulling then brings only the master's own change; the promoted entry is already the same on both sides.
        pull = role_merge.view(self.conn, self.role_id, role_merge.PULL)
        self.assertEqual([tuple(change["key"]) for change in pull["changes"]], [TUTOR_KEY])

    def test_nothing_accepted_is_unchanged(self) -> None:
        self.edit_role(cv(ANALYST))
        self.assertEqual(self.save(role_merge.PROMOTE)["unchanged"], True)
        self.assertEqual(self.master_cv()["id"], self.master_v1)


class PullTests(RoleMergeTestCase):
    def test_pull_keeps_role_removals_and_moves_the_base(self) -> None:
        self.edit_role(cv(ANALYST))  # the role dropped Tutor
        master_v2 = self.edit_master(cv(ANALYST + "\n- Also debugged it.", TUTOR, CLERK))
        result = self.save(role_merge.PULL)
        role_cv = self.role_cv()
        self.assertEqual((result["versionId"], role_cv["source"]), (role_cv["id"], "pull"))
        self.assertEqual(role_cv["content"], cv(ANALYST + "\n- Also debugged it.", CLERK))
        self.assertEqual(role_cv["base_master_id"], master_v2)
        self.assertTrue(result["baseMoved"])
        self.assertEqual(role_merge.view(self.conn, self.role_id, role_merge.PULL)["changes"], [])

    def test_conflicts_need_a_resolution(self) -> None:
        self.edit_role(cv(ANALYST + "\n- Role wording.", TUTOR))
        self.edit_master(cv(ANALYST + "\n- Master wording.", TUTOR))
        body = role_merge.view(self.conn, self.role_id, role_merge.PULL)
        self.assertEqual([(change["status"], change["accept"]) for change in body["changes"]], [("conflict", False)])
        with self.assertRaises(role_merge.MergeError):
            self.save(role_merge.PULL)
        edited = ANALYST + "\n- Both wordings."
        self.save(role_merge.PULL, resolutions={ANALYST_KEY: edited})
        self.assertEqual(self.role_cv()["content"], cv(edited, TUTOR))

    def test_blank_edit_drops_the_entry(self) -> None:
        _, resolutions = role_merge.parse_decisions(
            [], [{"key": list(ANALYST_KEY), "choice": "edit", "text": "  "},
                 {"key": list(TUTOR_KEY), "choice": "current"}, {"key": list(CLERK_KEY), "choice": "incoming"}],
        )
        self.assertEqual(
            resolutions, {ANALYST_KEY: None, TUTOR_KEY: cv_merge.KEEP_OURS, CLERK_KEY: cv_merge.TAKE_THEIRS}
        )

    def test_pull_with_nothing_to_merge_still_moves_the_base(self) -> None:
        master_v2 = self.edit_master(cv(ANALYST, TUTOR) + "\n")  # same units, different trailing layout
        body = role_merge.view(self.conn, self.role_id, role_merge.PULL)
        self.assertEqual((body["changes"], body["baseBehind"]), ([], True))
        result = self.save(role_merge.PULL)
        self.assertFalse(result["unchanged"])
        self.assertEqual(self.role_cv()["base_master_id"], master_v2)
        self.assertTrue(self.save(role_merge.PULL)["unchanged"])

    def test_stale_view_and_bad_decisions_are_refused(self) -> None:
        self.edit_master(cv(ANALYST, TUTOR, CLERK))
        body = role_merge.view(self.conn, self.role_id, role_merge.PULL)
        self.edit_role(cv(ANALYST))
        with self.assertRaises(role_merge.MergeError) as raised:
            self.save(role_merge.PULL, target_id=body["targetId"])
        self.assertEqual(raised.exception.status, 409)
        with self.assertRaises(role_merge.MergeError):
            self.save(role_merge.PULL, accept={("roles", "nope")})
        for accept, resolutions in (("x", []), ([["a"]], []), ([], [{"key": ["a", "b"], "choice": "maybe"}])):
            with self.assertRaises(role_merge.MergeError):
                role_merge.parse_decisions(accept, resolutions)


if __name__ == "__main__":
    unittest.main()
