import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
