# Task 5: import/export core and role CLI

**Status:** done. **Read:** [design § Cold start, import, export](../design.md#cold-start-import-export), D9, D11.

## Do

- `env_utils.parse_dotenv_text(text)` (keep `parse_dotenv_file` as a wrapper).
- `settings_io.py`: `env_import(conn, text, mode, dry_run)` → `{added, changed, unchanged, removed}`;
  `env_from_environment()` (catalogued keys from `os.environ`); `env_export(conn, reveal=False)` grouped and
  commented by catalog section, secrets masked.
- `examples/settings.example.env`: fictional, no real keys.
- `resumator` actions: `settings-import --env-file F [--replace] [--delete-after] [--from-environment]`,
  `settings-export [--reveal]`, `settings-set --key K` (value via `getpass` for secrets, else stdin),
  `settings-test --provider P`.

## Done when

Tests: import merge/replace/dry-run diffs; quoting and `export` lines; export masks and round-trips through import;
CLI actions against a temp `--db`.

## Handover

- `env_utils.parse_dotenv_text` added; `parse_dotenv_file` wraps it.
- `settings_io.py`: `env_import` (text) and `env_import_values` (dict; the CLI's `--from-environment` and task 6 can
  use it), `env_from_environment`, `env_export`, `is_secret` (catalog flag, or a KEY/TOKEN/SECRET/PASSWORD name for
  unknown keys such as `GEMINI_API_KEY`), `mask_secret` (`sk-…abcd`; ≤8 chars fully hidden). Diffs are sorted key
  lists, never values. A masked placeholder pasted back in is treated as unchanged (so task 6's PUT can reuse this).
- Export quotes only values the parser would mangle (spaces, `#`, quotes); round-trips with `--reveal`.
- CLI: `--dry-run` is shared with research; `settings-set` refuses empty values (no delete action yet);
  `settings-test` uses `settings_env.effective_env` and exits 1 on failure.
- `examples/settings.example.env` is fictional (swiftlet-style localhost OpenAI URL).
- Not run against a real provider or the real DB. The real `.env` still blocks startup until imported (task 9).
