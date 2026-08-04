import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend_registry import runtime_env
from env_utils import parse_dotenv_file


class EnvUtilsTests(unittest.TestCase):
    def test_parse_dotenv_file_handles_comments_export_and_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# comment",
                        "export FOO = bar",
                        "BAZ='quoted value'",
                        'QUX="double quoted"',
                        "EMPTY=",
                        "INVALID_LINE",
                    ]
                ),
                encoding="utf-8",
            )

            parsed = parse_dotenv_file(env_path)

            self.assertEqual(parsed["FOO"], "bar")
            self.assertEqual(parsed["BAZ"], "quoted value")
            self.assertEqual(parsed["QUX"], "double quoted")
            self.assertEqual(parsed["EMPTY"], "")
            self.assertNotIn("INVALID_LINE", parsed)

    def test_runtime_env_merges_os_and_env_file_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("SHARED=from_file\nFILE_ONLY=value\n", encoding="utf-8")

            with mock.patch("backend_registry.ENV_FILE_PATH", env_path):
                with mock.patch.dict(os.environ, {"SHARED": "from_os", "OS_ONLY": "value"}, clear=True):
                    merged = runtime_env()

            self.assertEqual(merged["SHARED"], "from_file")
            self.assertEqual(merged["OS_ONLY"], "value")
            self.assertEqual(merged["FILE_ONLY"], "value")


if __name__ == "__main__":
    unittest.main()
