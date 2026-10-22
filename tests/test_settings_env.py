import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import backend_registry
import settings_env
from cv_web import store

ROOT = Path(__file__).resolve().parent.parent


class EffectiveEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = store.connect(":memory:")
        self.addCleanup(self.conn.close)

    def test_db_values_win_over_shell_for_catalogued_keys(self) -> None:
        store.set_env_setting(self.conn, "OPENAI_MODEL", "from-db")
        base = {"OPENAI_MODEL": "from-shell", "OPENAI_API_KEY": "shell-key", "CV_THEME": "compact"}
        env = settings_env.effective_env(self.conn, base)
        self.assertEqual(env["OPENAI_MODEL"], "from-db")
        # A catalogued key set only in the shell is dropped, not passed through.
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CV_THEME", env)

    def test_uncatalogued_variables_pass_through(self) -> None:
        store.set_env_setting(self.conn, "SOMETHING_ELSE", "kept")
        env = settings_env.effective_env(self.conn, {"PATH": "/bin", "HOME": "/h"})
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h", "SOMETHING_ELSE": "kept"})

    def test_defaults_to_os_environ(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL_PROVIDER": "gemini", "RESUMATOR_PLAIN": "1"}):
            env = settings_env.effective_env(self.conn)
        self.assertNotIn("MODEL_PROVIDER", env)
        self.assertEqual(env["RESUMATOR_PLAIN"], "1")

    def test_shadowed_keys_lists_ignored_shell_values(self) -> None:
        base = {"OPENAI_API_KEY": "x", "CV_THEME": "", "PATH": "/bin"}
        self.assertEqual(settings_env.shadowed_keys(base), ["OPENAI_API_KEY"])

    def test_runtime_env_uses_stored_settings_without_a_file(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "shell"}):
            env = backend_registry.runtime_env({"OPENAI_API_KEY": "db"})
        self.assertEqual(env["OPENAI_API_KEY"], "db")


class OneShotEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "test.db"
        self.base = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "shell"})
        self.base.start()
        self.addCleanup(self.base.stop)

    def stored(self, key: str):
        conn = store.connect(self.db)
        try:
            return store.get_env_setting(conn, key)
        finally:
            conn.close()

    def test_missing_secret_without_terminal_fails_with_instructions(self) -> None:
        with self.assertRaises(settings_env.SettingsError) as raised:
            settings_env.one_shot_env(self.db, "openai", interactive=False)
        self.assertIn("OPENAI_API_KEY", str(raised.exception))
        self.assertIn("settings-set", str(raised.exception))

    def test_prompts_for_secret_and_saves_on_request(self) -> None:
        env = settings_env.one_shot_env(
            self.db, "openai", interactive=True, ask_secret=lambda _: " sk-typed ", ask_save=lambda _: "y"
        )
        self.assertEqual(env["OPENAI_API_KEY"], "sk-typed")
        self.assertEqual(self.stored("OPENAI_API_KEY"), "sk-typed")

    def test_prompted_secret_is_not_saved_by_default(self) -> None:
        env = settings_env.one_shot_env(
            self.db, "openai", interactive=True, ask_secret=lambda _: "sk-typed", ask_save=lambda _: ""
        )
        self.assertEqual(env["OPENAI_API_KEY"], "sk-typed")
        self.assertIsNone(self.stored("OPENAI_API_KEY"))

    def test_blank_secret_cancels(self) -> None:
        with self.assertRaises(settings_env.SettingsError):
            settings_env.one_shot_env(self.db, "openai", interactive=True, ask_secret=lambda _: " ")

    def test_stored_secret_needs_no_prompt(self) -> None:
        conn = store.connect(self.db)
        store.set_env_setting(conn, "OPENAI_API_KEY", "sk-db")
        conn.close()
        env = settings_env.one_shot_env(self.db, "openai", interactive=False)
        self.assertEqual(env["OPENAI_API_KEY"], "sk-db")

    def test_provider_without_secrets_never_prompts(self) -> None:
        env = settings_env.one_shot_env(self.db, "swiftlet", interactive=False)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_overrides_win_over_stored(self) -> None:
        conn = store.connect(self.db)
        store.set_env_setting(conn, "CV_FAST_MODE", "false")
        conn.close()
        env = settings_env.one_shot_env(self.db, "", {"CV_FAST_MODE": "true"}, interactive=False)
        self.assertEqual(env["CV_FAST_MODE"], "true")


class NoDotenvReadTests(unittest.TestCase):
    def test_no_code_path_opens_a_dotenv_file(self) -> None:
        pattern = re.compile(r"""ENV_FILE|["']\.env["']|load_dotenv_file|model_providers\.json""")
        sources = [
            *ROOT.glob("*.py"),
            *ROOT.glob("backends/*/module.py"),
            *ROOT.glob("cv_web/*.py"),
        ]
        offenders = [
            path.name
            for path in sources
            if not path.name.startswith("gemini-code") and pattern.search(path.read_text(encoding="utf-8"))
        ]
        # cv_web/server.py's raw "env" editor goes in task 7 (the Settings UI).
        self.assertEqual(sorted(offenders), ["server.py"])


if __name__ == "__main__":
    unittest.main()
