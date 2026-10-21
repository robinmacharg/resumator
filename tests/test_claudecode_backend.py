import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import provider_clients  # noqa: E402
from backends.claudecode import module as claudecode_module  # noqa: E402
from generate_cv import is_high_load_error  # noqa: E402

# Stands in for the real CLI: records argv, cwd and stdin, then prints the JSON in $FAKE_CLAUDE_REPLY.
FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
prompt = sys.stdin.read()
with open(os.environ["FAKE_CLAUDE_RECORD"], "w") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "prompt": prompt,
               "parent_env": os.environ.get("CLAUDECODE")}, fh)
sys.stdout.write(os.environ["FAKE_CLAUDE_REPLY"])
sys.exit(int(os.environ.get("FAKE_CLAUDE_RC", "0")))
"""


class ParseClaudeCodeOutputTests(unittest.TestCase):
    def test_success_returns_result_text(self):
        text, error = provider_clients.parse_claudecode_output(
            json.dumps({"type": "result", "is_error": False, "result": '{"a": 1}'})
        )
        self.assertEqual(text, '{"a": 1}')
        self.assertEqual(error, "")

    def test_error_includes_status_for_fallback_classification(self):
        text, error = provider_clients.parse_claudecode_output(
            json.dumps({"is_error": True, "result": "There's an issue with the selected model", "api_error_status": 404})
        )
        self.assertEqual(text, "")
        self.assertIn("status 404", error)
        self.assertTrue(is_high_load_error(error))

    def test_non_json_and_empty_results_are_errors(self):
        self.assertIn("non-JSON", provider_clients.parse_claudecode_output("oops")[1])
        self.assertIn("empty", provider_clients.parse_claudecode_output(json.dumps({"result": "  "}))[1])


class BuildClaudeCodeCommandTests(unittest.TestCase):
    def test_isolation_flags_and_overrides(self):
        command = provider_clients.build_claudecode_command(
            "sonnet", {"CLAUDECODE_SYSTEM_PROMPT": "custom", "CLAUDECODE_EFFORT": "high"}
        )
        self.assertEqual(command[:2], ["claude", "-p"])
        for flag in ("--safe-mode", "--no-session-persistence"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--model") + 1], "sonnet")
        self.assertEqual(command[command.index("--system-prompt") + 1], "custom")
        self.assertEqual(command[command.index("--effort") + 1], "high")

    def test_defaults(self):
        command = provider_clients.build_claudecode_command("opus", {})
        self.assertEqual(
            command[command.index("--system-prompt") + 1], provider_clients.CLAUDECODE_DEFAULT_SYSTEM_PROMPT
        )
        self.assertNotIn("--effort", command)


class ClaudeCodeBackendTests(unittest.TestCase):
    def setUp(self):
        self.backend = claudecode_module.get_backend()

    def test_model_sequence(self):
        self.assertEqual(self.backend.model_sequence({}, "haiku"), ["haiku"])
        self.assertEqual(self.backend.model_sequence({}), ["opus"])
        self.assertEqual(
            self.backend.model_sequence({"CLAUDECODE_MODEL": "sonnet", "CLAUDECODE_MODEL_FALLBACKS": "haiku, sonnet"}),
            ["sonnet", "haiku"],
        )

    def test_interrogate_disabled_by_env(self):
        status = self.backend.interrogate({"BACKEND_CLAUDECODE_ENABLED": "false"})
        self.assertFalse(status.enabled)

    def test_interrogate_requires_cli(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = empty_dir
            try:
                status = self.backend.interrogate({})
            finally:
                os.environ["PATH"] = old_path
        self.assertFalse(status.enabled)
        self.assertIn("not found", status.reason)


class RunClaudeCodeAttemptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp_path = Path(self.tmp.name)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.record_path = tmp_path / "record.json"
        self.log_dir = tmp_path / "logs"
        self.old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{self.old_path}"
        self.addCleanup(lambda: os.environ.__setitem__("PATH", self.old_path))

    def run_attempt(self, reply: dict, rc: int = 0):
        env = {
            **os.environ,
            "FAKE_CLAUDE_RECORD": str(self.record_path),
            "FAKE_CLAUDE_REPLY": json.dumps(reply),
            "FAKE_CLAUDE_RC": str(rc),
            "CLAUDECODE": "1",
        }
        return provider_clients.run_claudecode_attempt(
            model_name="haiku",
            prompt_text="PROMPT " * 5000,
            env=env,
            timeout_seconds=30,
            heartbeat_seconds=1,
            attempt_index=1,
            debug_log_dir=self.log_dir,
            log_prefix="test",
            emit_live_output=False,
        )

    def test_success_sends_prompt_on_stdin_from_neutral_cwd(self):
        result = self.run_attempt({"is_error": False, "result": "MODEL TEXT", "total_cost_usd": 0.01})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "MODEL TEXT")
        self.assertEqual(result.metadata["costUsd"], 0.01)
        record = json.loads(self.record_path.read_text())
        self.assertEqual(record["prompt"], "PROMPT " * 5000)
        self.assertNotEqual(Path(record["cwd"]).resolve(), ROOT_DIR)
        self.assertIn("resumator-claude-", record["cwd"])
        self.assertIsNone(record["parent_env"])
        self.assertTrue(result.log_path.exists())

    def test_cli_error_becomes_failed_attempt(self):
        result = self.run_attempt({"is_error": True, "result": "rate limited", "api_error_status": 429}, rc=1)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("status 429", result.stderr)


if __name__ == "__main__":
    unittest.main()
