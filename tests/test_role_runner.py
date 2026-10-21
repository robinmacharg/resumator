"""Tests for cv_web/role_runner.py: request from the store → `--io json` script → saved run row.

Runs use the real scripts as subprocesses on a temp DB, with a fake `claude` CLI on PATH as the provider.
"""

import base64
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
for path in (ROOT_DIR, ROOT_DIR / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cv_web import role_runner, store  # noqa: E402
from cv_web.role_runner import RunnerError  # noqa: E402
from test_claudecode_backend import FAKE_CLAUDE  # noqa: E402
from test_cv_source import MINIMAL  # noqa: E402
from test_generate_cv import valid_payload  # noqa: E402

HAS_RENDERER = bool(shutil.which("pandoc") and shutil.which("typst"))
CV_PROMPT = "Tailor the CV. Return JSON only."
RESEARCH_PROMPT = "Research the company."


class RoleRunnerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.conn = store.connect(self.tmp / "test.db")
        self.addCleanup(self.conn.close)
        store.add_cv_version(self.conn, MINIMAL, source="import")
        self.role_id = store.create_role(
            self.conn, "Engine Co Analyst", company="Engine Co", jobspec="Senior Analyst at Engine Co.",
            steering_text="lead with maths", theme="compact",
        )
        self.cv_id = store.seed_role_cv(self.conn, self.role_id)

        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.record_path = self.tmp / "record.json"
        self.base_env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "FAKE_CLAUDE_RECORD": str(self.record_path),
        }

    def env(self, reply_text: str) -> dict:
        return {**self.base_env, "FAKE_CLAUDE_REPLY": json.dumps({"is_error": False, "result": reply_text})}

    def sent_prompt(self) -> str:
        return json.loads(self.record_path.read_text(encoding="utf-8"))["prompt"]

    def fake_script(self, body: str) -> Path:
        script = self.tmp / "fake_script.py"
        script.write_text(body)
        return script


class BuildRequestTests(RoleRunnerTestCase):
    def test_cv_request_uses_the_role(self) -> None:
        request, cv_id = role_runner.build_cv_request(self.conn, self.role_id, prompt=f"  {CV_PROMPT}\n")
        self.assertEqual(cv_id, self.cv_id)
        self.assertEqual(request, {
            "cv": MINIMAL, "jobspec": "Senior Analyst at Engine Co.", "steering": "lead with maths",
            "prompt": CV_PROMPT, "theme": "compact", "provider": "", "model": "",
        })

    def test_cv_request_overrides_and_disabled_steering(self) -> None:
        request, _ = role_runner.build_cv_request(
            self.conn, self.role_id, prompt=CV_PROMPT, theme="", steering="", provider="openai", model="m"
        )
        self.assertEqual((request["theme"], request["steering"]), ("", ""))
        self.assertEqual((request["provider"], request["model"]), ("openai", "m"))

        store.update_role(self.conn, self.role_id, steering_enabled=False, theme=None)
        request, _ = role_runner.build_cv_request(self.conn, self.role_id, prompt=CV_PROMPT)
        self.assertEqual((request["theme"], request["steering"]), ("", ""))

    def test_cv_request_uses_the_newest_role_cv(self) -> None:
        edited = store.add_cv_version(self.conn, MINIMAL + "\n", source="edit", role_id=self.role_id)
        request, cv_id = role_runner.build_cv_request(self.conn, self.role_id, prompt=CV_PROMPT)
        self.assertEqual(cv_id, edited)
        self.assertEqual(request["cv"], MINIMAL + "\n")

    def test_default_prompt_comes_from_the_template_file(self) -> None:
        prompt_file = self.tmp / "prompt.md"
        prompt_file.write_text("\nFrom the file.\n")
        with mock.patch.object(role_runner, "CV_PROMPT_FILE", prompt_file):
            request, _ = role_runner.build_cv_request(self.conn, self.role_id)
        self.assertEqual(request["prompt"], "From the file.")
        prompt_file.write_text("  \n")
        with mock.patch.object(role_runner, "CV_PROMPT_FILE", prompt_file):
            with self.assertRaisesRegex(RunnerError, "empty"):
                role_runner.build_cv_request(self.conn, self.role_id)

    def test_research_request(self) -> None:
        request = role_runner.build_research_request(
            self.conn, self.role_id, urls=[" https://a.example ", "https://a.example", ""], prompt=RESEARCH_PROMPT
        )
        self.assertEqual(request["company"], "Engine Co")
        self.assertEqual(request["urls"], ["https://a.example"])
        self.assertEqual(request["jobspec"], "Senior Analyst at Engine Co.")
        self.assertFalse(request["dry_run"])

    def test_refusals(self) -> None:
        with self.assertRaisesRegex(RunnerError, "No role"):
            role_runner.build_cv_request(self.conn, 999, prompt=CV_PROMPT)
        bare = store.create_role(self.conn, "No CV")
        with self.assertRaisesRegex(RunnerError, "no CV"):
            role_runner.build_cv_request(self.conn, bare, prompt=CV_PROMPT)
        store.seed_role_cv(self.conn, bare)
        with self.assertRaisesRegex(RunnerError, "no company"):
            role_runner.build_research_request(self.conn, bare, prompt=RESEARCH_PROMPT)


class RunCvTests(RoleRunnerTestCase):
    def test_success_saves_a_current_run(self) -> None:
        reply = json.dumps(valid_payload())
        lines: list[str] = []
        started: list[object] = []
        outcome = role_runner.run_cv(
            self.conn, self.role_id, provider="claudecode", model="haiku", prompt=CV_PROMPT,
            on_log=lines.append, on_start=started.append, env=self.env(reply),
        )

        self.assertTrue(outcome.success, outcome.log)
        self.assertIsNone(outcome.error)
        self.assertEqual(len(started), 1)
        self.assertIn("--- attempt log ---", "".join(lines))
        self.assertEqual("".join(lines), outcome.log)
        self.assertIn("lead with maths", self.sent_prompt())

        run = store.get_cv_run(self.conn, outcome.run_id)
        self.assertEqual(store.current_cv_run(self.conn, self.role_id)["id"], outcome.run_id)
        self.assertEqual(run["cv_version_id"], self.cv_id)
        self.assertEqual((run["provider"], run["model"], run["theme"]), ("claudecode", "haiku", "compact"))
        self.assertEqual(run["steering_text"], "lead with maths")
        self.assertEqual(run["raw_output"], reply)
        self.assertEqual(run["model_json"]["metadata"]["steering"], "lead with maths")
        self.assertEqual(run["warnings_json"], outcome.result["warnings"])
        self.assertEqual(run["log"], outcome.log)
        self.assertIsNotNone(run["finished_at"])
        self.assertEqual(store.get_prompt(self.conn, run["prompt_hash"])["content"], CV_PROMPT)
        self.assertNotIn("pdf", " ".join(run))
        if HAS_RENDERER:
            self.assertTrue(base64.b64decode(outcome.pdf_base64).startswith(b"%PDF"))
            self.assertIsInstance(run["page_count"], int)

    def test_failed_run_is_saved_but_not_current(self) -> None:
        good = role_runner.run_cv(
            self.conn, self.role_id, provider="claudecode", model="haiku", prompt=CV_PROMPT,
            env=self.env(json.dumps(valid_payload())),
        )
        bad = role_runner.run_cv(
            self.conn, self.role_id, provider="claudecode", model="haiku", prompt=CV_PROMPT,
            env=self.env('{"candidate": {}}'),
        )

        self.assertFalse(bad.success)
        self.assertIn("JSON contract validation", bad.error)
        run = store.get_cv_run(self.conn, bad.run_id)
        self.assertEqual((run["success"], run["is_current"]), (0, 0))
        self.assertEqual(run["raw_output"], '{"candidate": {}}')
        self.assertTrue(run["log"].endswith(f"[runner] error: {bad.error}\n"))
        self.assertEqual(store.current_cv_run(self.conn, self.role_id)["id"], good.run_id)
        prompts = self.conn.execute("SELECT COUNT(*) FROM prompt_version").fetchone()[0]
        self.assertEqual(prompts, 1, "the same prompt text is stored once")

    def test_script_without_a_result(self) -> None:
        script = self.fake_script("import sys\nprint('boom', file=sys.stderr)\nsys.exit(3)\n")
        with mock.patch.object(role_runner, "CV_SCRIPT", script):
            outcome = role_runner.run_cv(self.conn, self.role_id, prompt=CV_PROMPT)
        self.assertFalse(outcome.success)
        self.assertIn("no JSON result (exit code 3)", outcome.error)
        run = store.get_cv_run(self.conn, outcome.run_id)
        self.assertIn("boom", run["log"])
        self.assertIn("[runner] error:", run["log"])

    def test_script_receives_the_request_on_stdin(self) -> None:
        script = self.fake_script(
            "import json, sys\n"
            "request = json.loads(sys.stdin.read())\n"
            "print('working', file=sys.stderr)\n"
            "print(json.dumps({'success': True, 'error': None, 'provider': 'p', 'model': 'm',\n"
            "                  'raw_output': request['cv'], 'model_json': {'echo': request['steering']},\n"
            "                  'warnings': ['w'], 'page_count': 2, 'pdf_base64': 'UERG'}))\n"
        )
        with mock.patch.object(role_runner, "CV_SCRIPT", script):
            outcome = role_runner.run_cv(self.conn, self.role_id, prompt=CV_PROMPT, make_current=False)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.pdf_base64, "UERG")
        run = store.get_cv_run(self.conn, outcome.run_id)
        self.assertEqual(run["raw_output"], MINIMAL)
        self.assertEqual(run["model_json"], {"echo": "lead with maths"})
        self.assertEqual((run["warnings_json"], run["page_count"], run["is_current"]), (["w"], 2, 0))
        self.assertEqual(run["log"], "working\n")


class RunResearchTests(RoleRunnerTestCase):
    def test_success_saves_a_current_run(self) -> None:
        outcome = role_runner.run_research(
            self.conn, self.role_id, urls=["https://engine.example"], provider="claudecode", model="haiku",
            prompt=RESEARCH_PROMPT, env=self.env("## Notes\nEngines."),
        )
        self.assertTrue(outcome.success, outcome.log)
        run = store.get_research_run(self.conn, outcome.run_id)
        self.assertEqual(store.current_research_run(self.conn, self.role_id)["id"], outcome.run_id)
        self.assertEqual((run["company"], run["urls_json"], run["dry_run"]), ("Engine Co", ["https://engine.example"], 0))
        self.assertEqual(run["output_json"]["output"], "## Notes\nEngines.")
        self.assertIn("## Notes\nEngines.", run["output_md"])
        self.assertEqual((run["provider"], run["model"]), ("claudecode", "haiku"))
        self.assertEqual(store.get_prompt(self.conn, run["prompt_hash"])["kind"], "research")
        self.assertIn("Engine Co", self.sent_prompt())

    def test_dry_run(self) -> None:
        outcome = role_runner.run_research(
            self.conn, self.role_id, company="Other Co", dry_run=True, prompt=RESEARCH_PROMPT,
            env=self.base_env,
        )
        self.assertTrue(outcome.success, outcome.log)
        run = store.get_research_run(self.conn, outcome.run_id)
        self.assertEqual((run["company"], run["dry_run"]), ("Other Co", 1))
        self.assertTrue(run["output_json"]["dryRun"])
        self.assertFalse(self.record_path.exists())


if __name__ == "__main__":
    unittest.main()
