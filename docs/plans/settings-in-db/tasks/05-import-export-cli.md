# Task 5: import/export core and role CLI

**Status:** todo. **Read:** [design § Cold start, import, export](../design.md#cold-start-import-export), D9, D11.

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

(fill in at the end of the task)
