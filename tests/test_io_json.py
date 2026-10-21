"""Contract tests for `--io json` (multi-role R14): request on stdin, one JSON result on stdout, no files written.

Each script runs as a real subprocess from an empty temp cwd, with a fake `claude` CLI on PATH as the provider.
"""

import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
for path in (ROOT_DIR, ROOT_DIR / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from test_claudecode_backend import FAKE_CLAUDE  # noqa: E402
from test_cv_source import MINIMAL  # noqa: E402
from test_generate_cv import valid_payload  # noqa: E402

HAS_RENDERER = bool(shutil.which("pandoc") and shutil.which("typst"))


class IoJsonTestCase(unittest.TestCase):
    def setUp(self) -> None:
        cwd = tempfile.TemporaryDirectory()
        tools = tempfile.TemporaryDirectory()
        self.addCleanup(cwd.cleanup)
        self.addCleanup(tools.cleanup)
        self.cwd = Path(cwd.name)
        bin_dir = Path(tools.name) / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.record_path = Path(tools.name) / "record.json"
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "FAKE_CLAUDE_RECORD": str(self.record_path),
        }

    def run_script(self, script: str, request: object, reply_text: str = "") -> tuple[int, dict, str]:
        """Run `script --io json` with the request on stdin; return (exit code, result, stderr)."""
        env = {**self.env, "FAKE_CLAUDE_REPLY": json.dumps({"is_error": False, "result": reply_text})}
        stdin = request if isinstance(request, str) else json.dumps(request)
        completed = subprocess.run(
            [sys.executable, str(ROOT_DIR / script), "--io", "json"],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=self.cwd,
            env=env,
            timeout=120,
        )
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1, f"stdout must be one JSON line, got: {completed.stdout!r}")
        self.assertEqual(os.listdir(self.cwd), [], "nothing may be written to the working directory")
        return completed.returncode, json.loads(lines[0]), completed.stderr

    def sent_prompt(self) -> str:
        return json.loads(self.record_path.read_text(encoding="utf-8"))["prompt"]


class GenerateCvIoJsonTests(IoJsonTestCase):
    def request(self, **overrides: object) -> dict:
        return {
            "cv": MINIMAL,
            "jobspec": "Senior Analyst at Engine Co.",
            "steering": "lead with maths",
            "prompt": "Tailor the CV. Return JSON only.",
            "theme": "compact",
            "provider": "claudecode",
            "model": "haiku",
            **overrides,
        }

    def test_success_returns_the_run_without_files(self) -> None:
        reply = json.dumps(valid_payload())
        code, result, stderr = self.run_script("generate_cv.py", self.request(), reply)

        self.assertEqual(code, 0, stderr)
        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])
        self.assertEqual((result["provider"], result["model"]), ("claudecode", "haiku"))
        self.assertEqual(result["raw_output"], reply)
        metadata = result["model_json"]["metadata"]
        self.assertEqual(metadata["steering"], "lead with maths")
        self.assertEqual(metadata["warnings"], result["warnings"])
        self.assertIn("--- attempt log ---", stderr)
        self.assertIn("Senior Analyst at Engine Co.", self.sent_prompt())
        self.assertIn("lead with maths", self.sent_prompt())
        if HAS_RENDERER:
            self.assertTrue(base64.b64decode(result["pdf_base64"]).startswith(b"%PDF"))
            self.assertEqual(metadata["page_count"], result["page_count"])
            self.assertIsInstance(result["page_count"], int)

    def test_invalid_request(self) -> None:
        code, result, _ = self.run_script("generate_cv.py", self.request(cv=""))
        self.assertEqual(code, 1)
        self.assertFalse(result["success"])
        self.assertIn("invalid request", result["error"])
        self.assertIn("'cv'", result["error"])

        code, result, _ = self.run_script("generate_cv.py", "not json")
        self.assertEqual(code, 1)
        self.assertIn("invalid request", result["error"])

    def test_contract_failure_keeps_the_raw_output(self) -> None:
        code, result, stderr = self.run_script("generate_cv.py", self.request(), '{"candidate": {}}')
        self.assertEqual(code, 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["raw_output"], '{"candidate": {}}')
        self.assertIn("JSON contract validation", result["error"])
        self.assertIsNone(result["pdf_base64"])
        self.assertIn("failed JSON contract validation", stderr)


class ResearchRoleIoJsonTests(IoJsonTestCase):
    def request(self, **overrides: object) -> dict:
        return {
            "cv": MINIMAL,
            "jobspec": "Senior Analyst at Engine Co.",
            "prompt": "Research the company.",
            "company": "Engine Co",
            "urls": ["https://engine.example", "https://engine.example"],
            "provider": "claudecode",
            "model": "haiku",
            **overrides,
        }

    def test_success_returns_the_notes_without_files(self) -> None:
        code, result, stderr = self.run_script("research_role.py", self.request(), "## Notes\nEngines.")

        self.assertEqual(code, 0, stderr)
        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])
        self.assertEqual((result["provider"], result["model"]), ("claudecode", "haiku"))
        self.assertTrue(result["output_md"].startswith("Generated At: "))
        self.assertIn("## Notes\nEngines.", result["output_md"])
        envelope = result["output_json"]
        self.assertEqual(envelope["output"], "## Notes\nEngines.")
        self.assertEqual(envelope["companyName"], "Engine Co")
        self.assertEqual(envelope["urls"], ["https://engine.example"])
        self.assertIn("--- attempt log ---", stderr)
        self.assertIn("Engine Co", self.sent_prompt())

    def test_dry_run_builds_the_prompt_only(self) -> None:
        code, result, _ = self.run_script("research_role.py", self.request(dry_run=True))
        self.assertEqual(code, 0)
        self.assertTrue(result["output_json"]["dryRun"])
        self.assertIn("Engine Co", result["output_json"]["promptPreview"])
        self.assertIsNone(result["output_md"])
        self.assertFalse(self.record_path.exists())

    def test_invalid_request(self) -> None:
        code, result, _ = self.run_script("research_role.py", self.request(urls="https://engine.example"))
        self.assertEqual(code, 1)
        self.assertIn("'urls'", result["error"])


class RunJsonIoTests(IoJsonTestCase):
    def test_stray_stdout_goes_to_stderr(self) -> None:
        script = (
            "import subprocess, sys\n"
            "from pipe_io import run_json_io\n"
            "def handler(request):\n"
            "    print('python noise')\n"
            "    subprocess.run(['echo', 'child noise'])\n"
            "    return {'success': True, 'echo': request['x'], 'error': None}\n"
            "sys.exit(run_json_io(handler))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            input='{"x": 1}',
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout), {"success": True, "echo": 1, "error": None})
        self.assertIn("python noise", completed.stderr)
        self.assertIn("child noise", completed.stderr)


if __name__ == "__main__":
    unittest.main()
