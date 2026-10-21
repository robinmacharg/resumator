"""Tests for cv_web/server_roles.py: the role API over a temp DB (rendering and role runs are patched)."""

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
for path in (ROOT_DIR, ROOT_DIR / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cv_web import role_runner, server_roles, store  # noqa: E402
from cv_web import server_runtime_state as runtime  # noqa: E402
from test_cv_source import MINIMAL  # noqa: E402
from test_generate_cv import valid_payload  # noqa: E402


class _Handler:
    def __init__(self) -> None:
        self.responses: list[tuple[int, object]] = []
        self.documents: list[tuple[bytes, str, str | None]] = []

    def _json_response(self, payload, status=200):
        self.responses.append((status, payload))

    def _bytes_response(self, data, content_type, *, filename=None):
        self.documents.append((data, content_type, filename))


class ServerRolesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = Path(tmp.name) / "test.db"
        patcher = mock.patch.object(server_roles, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = store.connect(db_path)
        self.addCleanup(self.conn.close)
        self.master_id = store.add_cv_version(self.conn, MINIMAL, source="import")
        self.role_id = store.create_role(self.conn, "Engine Co Analyst", company="Engine Co", jobspec="Analyst.")
        self.cv_id = store.seed_role_cv(self.conn, self.role_id)
        server_roles.RENDER_CACHE.clear()
        self.addCleanup(server_roles.RENDER_CACHE.clear)
        self.deps = {"RUN_LOCK": threading.Lock(), "RESEARCH_RUN_LOCK": threading.Lock()}

    def call(self, method: str, path: str, payload=None, query: str = ""):
        handler = _Handler()
        handled = server_roles.dispatch(handler, method, SimpleNamespace(path=path, query=query), payload, self.deps)
        self.assertTrue(handled, path)
        return handler

    def json(self, method: str, path: str, payload=None, query: str = "", status: int = 200):
        handler = self.call(method, path, payload, query)
        self.assertEqual(len(handler.responses), 1)
        got_status, body = handler.responses[0]
        self.assertEqual(got_status, status, body)
        return body

    def add_run(self, *, success: bool = True, theme: str | None = None) -> int:
        return store.add_cv_run(
            self.conn, self.role_id, self.cv_id, success=success, theme=theme,
            raw_output=json.dumps(valid_payload()) if success else None,
        )


class RoutingTests(ServerRolesTestCase):
    def test_other_routes_are_not_ours(self) -> None:
        handler = _Handler()
        for method, path in (("GET", "/api/state"), ("POST", "/api/roles/1/nope"), ("GET", "/api/roles/x")):
            self.assertFalse(server_roles.dispatch(handler, method, SimpleNamespace(path=path, query=""), {}, {}))
        self.assertEqual(handler.responses, [])

    def test_unknown_role_is_404(self) -> None:
        body = self.json("GET", "/api/roles/999", status=404)
        self.assertEqual(body["error"], "No role 999")


class RoleTests(ServerRolesTestCase):
    def test_list_and_get_use_camel_case(self) -> None:
        roles = self.json("GET", "/api/roles")["roles"]
        self.assertEqual([role["id"] for role in roles], [self.role_id])
        self.assertIn("steeringEnabled", roles[0])
        self.assertIn("lastRunAt", roles[0])
        self.assertEqual(self.json("GET", f"/api/roles/{self.role_id}")["role"]["company"], "Engine Co")

    def test_create_seeds_the_cv_from_the_master(self) -> None:
        body = self.json("POST", "/api/roles", {"name": "Second", "company": "B Ltd", "jobspec": "Spec",
                                                "theme": "compact", "steeringEnabled": False})
        role = body["role"]
        self.assertEqual((role["slug"], role["theme"], role["steeringEnabled"]), ("second", "compact", 0))
        cv = store.current_cv_version(self.conn, role["id"])
        self.assertEqual((cv["source"], cv["base_master_id"], cv["content"]), ("seed", self.master_id, MINIMAL))

    def test_create_refusals(self) -> None:
        self.json("POST", "/api/roles", {"name": " "}, status=400)
        self.json("POST", "/api/roles", {"name": "X", "colour": "red"}, status=400)
        self.json("POST", "/api/roles", {"name": "X", "theme": "nope"}, status=400)
        self.json("POST", "/api/roles", {"name": "X", "steeringEnabled": "yes"}, status=400)
        self.assertEqual(len(store.list_roles(self.conn)), 1)

    def test_create_needs_a_master(self) -> None:
        self.conn.execute("DELETE FROM cv_version")
        body = self.json("POST", "/api/roles", {"name": "X"}, status=409)
        self.assertIn("master", body["error"])

    def test_update_and_archive(self) -> None:
        role = self.json("POST", f"/api/roles/{self.role_id}", {"status": "closed", "steeringText": "lead"})["role"]
        self.assertEqual((role["status"], role["steeringText"]), ("closed", "lead"))
        self.assertEqual(self.json("GET", "/api/roles", query="status=closed")["roles"][0]["id"], self.role_id)
        self.json("POST", f"/api/roles/{self.role_id}", {"status": "gone"}, status=400)
        self.json("POST", f"/api/roles/{self.role_id}", {}, status=400)
        role = self.json("POST", f"/api/roles/{self.role_id}", {"theme": ""})["role"]
        self.assertIsNone(role["theme"])

    def test_delete(self) -> None:
        self.add_run()
        self.json("POST", f"/api/roles/{self.role_id}/delete")
        self.assertIsNone(store.get_role(self.conn, self.role_id))
        self.assertIsNotNone(store.current_cv_version(self.conn, None))

    def test_delete_refused_while_its_run_is_live(self) -> None:
        runtime.set_current_run({"running": True, "roleId": self.role_id})
        self.addCleanup(runtime.CURRENT_RUN.clear)
        self.json("POST", f"/api/roles/{self.role_id}/delete", status=409)


class CvTests(ServerRolesTestCase):
    def test_role_cv_save_adds_an_edit_version(self) -> None:
        body = self.json("GET", f"/api/roles/{self.role_id}/cv")
        self.assertEqual((body["cv"]["id"], len(body["versions"])), (self.cv_id, 1))
        self.assertNotIn("content", body["versions"][0])

        body = self.json("POST", f"/api/roles/{self.role_id}/cv", {"content": MINIMAL + "\nMore.\n", "note": "n"})
        self.assertFalse(body["unchanged"])
        self.assertEqual((body["cv"]["source"], body["cv"]["baseMasterId"]), ("edit", self.master_id))
        self.assertEqual(len(body["versions"]), 2)

        body = self.json("POST", f"/api/roles/{self.role_id}/cv", {"content": MINIMAL + "\nMore.\n"})
        self.assertTrue(body["unchanged"])
        self.assertEqual(len(body["versions"]), 2)
        self.json("POST", f"/api/roles/{self.role_id}/cv", {"content": 3}, status=400)

    def test_master_cv(self) -> None:
        self.assertEqual(self.json("GET", "/api/master/cv")["cv"]["id"], self.master_id)
        body = self.json("POST", "/api/master/cv", {"content": "# new master\n"})
        self.assertEqual((body["cv"]["source"], body["cv"]["roleId"]), ("edit", None))
        self.assertEqual(store.current_cv_version(self.conn, self.role_id)["id"], self.cv_id)


class MergeTests(ServerRolesTestCase):
    def test_promote_round_trip(self) -> None:
        role_cv = MINIMAL + "\n## Tutor | Home\nDates: 2018\n\n- Taught maths.\n"
        store.add_cv_version(self.conn, role_cv, source="edit", role_id=self.role_id)
        path = f"/api/roles/{self.role_id}/merge"
        view = self.json("GET", path, query="direction=promote")
        self.assertEqual([(c["key"], c["status"], c["accept"]) for c in view["changes"]],
                         [(["roles", "tutor | home"], "added", True)])
        body = self.json("POST", path, {
            "direction": "promote", "targetId": view["targetId"], "sourceId": view["sourceId"],
            "accept": [c["key"] for c in view["changes"]], "resolutions": [], "note": "from role",
        })
        self.assertEqual((body["unchanged"], body["baseMoved"]), (False, True))
        self.assertEqual(body["masterCv"]["cv"]["content"], role_cv)
        self.assertEqual((body["masterCv"]["cv"]["source"], body["masterCv"]["cv"]["note"]), ("promote", "from role"))
        self.assertEqual(body["roleCv"]["cv"]["baseMasterId"], body["versionId"])

    def test_refusals(self) -> None:
        path = f"/api/roles/{self.role_id}/merge"
        self.json("GET", path, query="direction=up", status=400)
        view = self.json("GET", path, query="direction=pull")
        self.json("POST", path, {"direction": "pull", "targetId": "1", "sourceId": 1}, status=400)
        stale = {"direction": "pull", "targetId": view["targetId"] + 99, "sourceId": view["sourceId"]}
        self.json("POST", path, stale, status=409)
        self.json("POST", path, {**stale, "targetId": view["targetId"], "accept": "all"}, status=400)


class HistoryAndImportTests(ServerRolesTestCase):
    def test_version_read_and_restore(self) -> None:
        store.add_cv_version(self.conn, MINIMAL + "\nMore.\n", source="edit", role_id=self.role_id)
        path = f"/api/roles/{self.role_id}/cv/versions/{self.cv_id}"
        self.assertEqual(self.json("GET", path)["version"]["content"], MINIMAL)
        body = self.json("POST", path + "/restore")
        self.assertEqual((body["cv"]["content"], body["cv"]["note"]), (MINIMAL, f"Restored version {self.cv_id}"))
        self.assertEqual((body["cv"]["source"], body["unchanged"]), ("edit", False))
        self.assertTrue(self.json("POST", path + "/restore")["unchanged"])

        master_path = f"/api/master/cv/versions/{self.master_id}"
        self.assertEqual(self.json("GET", master_path)["version"]["roleId"], None)
        self.assertTrue(self.json("POST", master_path + "/restore")["unchanged"])
        # A version of another CV is 404 on both sides.
        self.json("GET", f"/api/master/cv/versions/{self.cv_id}", status=404)
        self.json("GET", f"/api/roles/{self.role_id}/cv/versions/{self.master_id}", status=404)

    def test_import_round_trip(self) -> None:
        cv_path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "CV.md"
        self.enterContext(mock.patch.object(server_roles, "IMPORT_PATH", cv_path))
        cv_path.write_text(MINIMAL + "\n# Education\n\n## School\nDates: 2000\n", encoding="utf-8")
        view = self.json("GET", "/api/master/import")
        self.assertEqual([c["key"] for c in view["changes"]], [["education", ""], ["education", "school"]])
        body = self.json("POST", "/api/master/import", {
            "targetId": view["targetId"], "sourceHash": view["sourceHash"],
            "accept": [c["key"] for c in view["changes"]], "resolutions": [],
        })
        self.assertEqual(body["masterCv"]["cv"]["source"], "import")
        self.assertIn("## School", body["masterCv"]["cv"]["content"])
        self.json("POST", "/api/master/import", {"targetId": view["targetId"], "sourceHash": 1}, status=400)
        self.json("POST", "/api/master/import", {"targetId": view["targetId"], "sourceHash": "x"}, status=409)


class RunTests(ServerRolesTestCase):
    def test_list_get_and_select(self) -> None:
        first = self.add_run()
        second = self.add_run()
        failed = self.add_run(success=False)
        body = self.json("GET", f"/api/roles/{self.role_id}/runs")
        self.assertEqual([run["id"] for run in body["cvRuns"]], [failed, second, first])
        self.assertEqual(body["researchRuns"], [])
        self.assertNotIn("rawOutput", body["cvRuns"][0])
        self.assertIn("rawOutput", self.json("GET", f"/api/roles/{self.role_id}/runs/cv/{first}")["run"])

        body = self.json("POST", f"/api/roles/{self.role_id}/runs/cv/{first}/current")
        self.assertEqual([run["id"] for run in body["cvRuns"] if run["isCurrent"]], [first])
        self.json("POST", f"/api/roles/{self.role_id}/runs/cv/{failed}/current", status=400)

    def test_runs_of_another_role_are_404(self) -> None:
        run_id = self.add_run()
        other = store.create_role(self.conn, "Other")
        self.json("GET", f"/api/roles/{other}/runs/cv/{run_id}", status=404)
        self.json("POST", f"/api/roles/{other}/runs/cv/{run_id}/current", status=404)


class DocumentTests(ServerRolesTestCase):
    def test_render_is_cached_per_run_theme_and_format(self) -> None:
        run_id = self.add_run(theme="compact")
        path = f"/api/roles/{self.role_id}/runs/cv/{run_id}/cv"
        with mock.patch.object(server_roles, "render_cv", return_value=b"%PDF-x") as render:
            handler = self.call("GET", path + ".pdf")
            self.call("GET", path + ".pdf", query="theme=compact")
            self.call("GET", path + ".pdf", query="theme=")
            self.call("GET", path + ".docx", query="theme=compact")
            self.call("GET", path + ".docx")
        self.assertEqual(handler.documents, [(b"%PDF-x", "application/pdf", f"engine-co-analyst-run{run_id}.pdf")])
        self.assertEqual([call.args[1:] for call in render.call_args_list],
                         [("pdf", "compact"), ("pdf", None), ("docx", None)])
        markdown = render.call_args_list[0].args[0]
        self.assertIn("[candidate_name] Ada Lovelace", markdown)

    def test_refusals(self) -> None:
        failed = self.add_run(success=False)
        run_id = self.add_run()
        self.json("GET", f"/api/roles/{self.role_id}/runs/cv/{failed}/cv.pdf", status=409)
        self.json("GET", f"/api/roles/{self.role_id}/runs/cv/{run_id}/cv.pdf", query="theme=nope", status=400)
        with mock.patch.object(server_roles, "render_cv", return_value=None):
            self.json("GET", f"/api/roles/{self.role_id}/runs/cv/{run_id}/cv.pdf", status=500)

    @unittest.skipUnless(server_roles.available_themes(), "no themes")
    def test_real_render(self) -> None:
        import shutil
        if not (shutil.which("pandoc") and shutil.which("typst")):
            self.skipTest("needs pandoc and typst")
        run_id = self.add_run()
        handler = self.call("GET", f"/api/roles/{self.role_id}/runs/cv/{run_id}/cv.pdf")
        self.assertTrue(handler.documents[0][0].startswith(b"%PDF"))


class StartRunTests(ServerRolesTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(runtime.CURRENT_RUN.clear)
        self.addCleanup(runtime.LAST_RUN.clear)
        self.addCleanup(runtime.CURRENT_RESEARCH_RUN.clear)
        self.addCleanup(runtime.LAST_RESEARCH_RUN.clear)

    def wait_for(self, lock: threading.Lock) -> None:
        deadline = time.monotonic() + 5
        while lock.locked() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(lock.locked())

    def test_cv_run_publishes_state_and_warms_the_cache(self) -> None:
        def fake_run_cv(conn, role_id, *, on_log, **options):
            self.assertEqual(options["theme"], "compact")
            on_log("working\n")
            run_id = store.add_cv_run(conn, role_id, self.cv_id, success=True, theme="compact")
            return role_runner.RunOutcome(run_id, True, None, "working\n", {}, "JVBERi0=")  # "%PDF-"

        with mock.patch.object(role_runner, "run_cv", side_effect=fake_run_cv):
            body = self.json("POST", f"/api/roles/{self.role_id}/runs/cv", {"theme": "compact"})
            self.assertTrue(body["running"])
            self.wait_for(self.deps["RUN_LOCK"])
        last = runtime.LAST_RUN
        self.assertEqual((last["roleId"], last["success"], last["kind"]), (self.role_id, True, "role-cv"))
        self.assertIn("working", last["output"])
        self.assertEqual(server_roles.RENDER_CACHE.get((last["runId"], "compact", "pdf")), b"%PDF-")

    def test_failed_run_still_finishes_and_releases_the_lock(self) -> None:
        with mock.patch.object(role_runner, "run_cv", side_effect=RuntimeError("boom")):
            self.json("POST", f"/api/roles/{self.role_id}/runs/cv", {})
            self.wait_for(self.deps["RUN_LOCK"])
        self.assertEqual((runtime.LAST_RUN["success"], runtime.LAST_RUN["error"]), (False, "boom"))
        self.assertIn("[runner] error: boom", runtime.LAST_RUN["output"])

    def test_refusals_come_back_before_starting(self) -> None:
        self.json("POST", f"/api/roles/{self.role_id}/runs/cv", {"theme": "nope"}, status=400)
        self.json("POST", f"/api/roles/{self.role_id}/runs/research", {"company": " "}, status=400)
        self.json("POST", f"/api/roles/{self.role_id}/runs/research", {"urls": "x"}, status=400)
        self.deps["RUN_LOCK"].acquire()
        body = self.json("POST", f"/api/roles/{self.role_id}/runs/cv", {}, status=409)
        self.assertEqual(body["error"], "A run is already in progress")

    def test_research_run(self) -> None:
        def fake_run_research(conn, role_id, *, on_log, on_start, **options):
            self.assertEqual((options["company"], options["urls"], options["dry_run"]),
                             (None, ["https://a.example"], True))
            run_id = store.add_research_run(conn, role_id, success=True, company="Engine Co")
            return role_runner.RunOutcome(run_id, True, None, "")

        with mock.patch.object(role_runner, "run_research", side_effect=fake_run_research):
            self.json("POST", f"/api/roles/{self.role_id}/runs/research",
                      {"urls": ["https://a.example"], "dryRun": True})
            self.wait_for(self.deps["RESEARCH_RUN_LOCK"])
        last = runtime.LAST_RESEARCH_RUN
        self.assertEqual((last["roleId"], last["success"], last["companyName"]), (self.role_id, True, ""))
        self.assertIsNotNone(last["runId"])


if __name__ == "__main__":
    unittest.main()
