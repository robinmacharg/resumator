# Settings in the DB: design

Design record for [index.md](index.md). Tasks link to the sections they need; read only those. Decisions are
numbered D1–D11 and cited by number in tasks and the log.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **New `env_setting` table**; `setting` stays for internal app state | Your call. Import, export and wipe touch only user config |
| D2 | **Secrets stored as plain text for now.** Programmatic backups (`store.backup`, `--action backup`) should later exclude, redact or encrypt them: logged as a Security TODO | Your call |
| D3 | **Provider test makes one real model call** | Your call. Proving the key and model work is the point |
| D4 | **`.env` is never read** by the server, role CLI or scripts | Your call |
| D5 | **Fast mode stays a global setting** (`CV_FAST_MODE`). Low value now that it truncates the CV; a candidate for removal later | Your call |
| D6 | **One-shot scripts read the DB as well**; R5's "scripts stay DB-free" is superseded for config | Your call. No file-based config anywhere |
| D7 | **Startup audit refuses to run if a `.env` is present** (see "Startup audit"). Settings import is the one action still allowed, so you can migrate | Your call. Also stops the `gemini` CLI picking up a stray `.env` (I believe it searches the current folder and its parents) |
| D8 | **Shell environment variables don't override catalogued keys.** Keys the catalog declares are removed from `os.environ` before the DB values are applied; other variables (`PATH`, `HOME`, …) pass through | Your call. A stray `export OPENAI_API_KEY=…` can't silently replace the DB value |
| D9 | **Secrets are never accepted as CLI arguments or `KEY=… cmd` prefixes.** A missing key is prompted for with `getpass` (on a terminal, with an offer to save it) or the run fails with how to set it | Your call. Arguments show up in `ps` and history; prefixes go into history and child processes |
| D10 | **`model_providers.json` is removed.** The backend modules are the only catalog | Your call. It's stale file config, used only as a fallback when no backends are found |
| D11 | **One precedence rule for every catalogued key, secret or not.** One-off non-secret overrides are CLI flags (`--fast`, `--font-priority`; `--theme`/`--provider`/`--model` exist). The audit warns when a stripped key is set in the shell, and import offers "current environment" as a source | Your call. What the Settings page and export show is exactly what ran |

## Today

| Where | What it does with `.env` |
|---|---|
| `backend_registry.runtime_env` | `os.environ` + `.env` (`.env` wins). Used for `/api/state` provider interrogation |
| `generate_cv.main`, `research_role.main` | Each re-reads `.env` over `os.environ` (own copy of the parser), in both modes. Both also load `model_providers.json` |
| `role_runner.run_script` | Spawns the scripts with `env=None`, so the script's own `.env` read decides |
| UI "Env" tab (`EDITOR_FILES["env"]`) | Raw text editor over the `.env` file, readable and writable over the API |
| `store.setting` | `key TEXT PK, value TEXT`. Internal state: `first_run_done`, `role_merge` import base |

The keys the code reads are listed per backend in [docs/backends.md](../backends.md), plus these globals: `MODEL_PROVIDER`,
`CV_FAST_MODE`, `CV_THEME`, `CV_FONT_PRIORITY`, `RESEARCH_GEMINI_*`, `GEMINI_CLI_TRUST_WORKSPACE`. Some keys are only passed
through to a CLI (for example `GEMINI_API_KEY` for `gemini`).

## Design

### Storage

```sql
CREATE TABLE env_setting (
    key TEXT PRIMARY KEY,          -- the env var name, e.g. OPENAI_API_KEY
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Built `store` functions: `list_env_settings`, `env_settings`, `get_env_setting`, `set_env_setting`, `delete_env_setting`, and
`replace_env_settings` (one transaction). Information about each key lives in code (next section), not the DB.

### Settings catalog (code)

- **Backend contract:** an optional member `settings() -> list[SettingSpec]` in `backends/base.py`.
  `SettingSpec(key, label, secret=False, default=None, kind="text"|"bool"|"int"|"csv"|"choice", choices=None, help="")`.
  Backends without it still work, and their keys appear under "Other".
- **Globals:** `settings_catalog.py` declares `MODEL_PROVIDER` (choice over the registered ids), `CV_FAST_MODE`,
  `CV_THEME` (choice over `themes/`), `CV_FONT_PRIORITY`, and `RESEARCH_GEMINI_*` (Advanced).
  `catalog_keys()` returns every declared key (used by D8).
- **Unknown keys** stored in the DB (for example `GEMINI_API_KEY`) are kept, shown under "Other", and passed through.

### Effective environment

A new module `settings_env.py` (repo root, so the scripts can import it) provides
`effective_env(conn) -> dict[str, str]`: `os.environ`, minus `catalog_keys()` (D8), plus the DB rows.

| Caller | Change |
|---|---|
| Server `/api/state`, provider test | `backend_registry.runtime_env(overrides)`; the `.env` read is removed |
| `role_runner.run_cv` / `run_research` | Pass `env=effective_env(conn)` to the script |
| `generate_cv` / `research_role`, `--io json` | Use the `env` they were given, unchanged: no file read, no DB (the caller already resolved it) |
| `generate_cv` / `research_role`, one-shot | Open the DB (`--db` flag, default `cv_web/resumator.db`) and call `effective_env`. Apply D9 when the chosen provider is missing a key |
| `env_utils.parse_dotenv_file` | Kept, now parsing text, used only for import. `generate_cv.load_dotenv_file` is deleted |

Providers are re-interrogated on every `/api/state`, so a saved change takes effect without a restart.

### Startup audit

`startup_audit.py`: a list of checks, each returning findings with `error` (refuse to run) or `warn` (log it).
`run_audit(root) -> list[Finding]` is called by `python3 -m cv_web`, `python3 -m resumator`, and the one-shot
scripts.

| Check | Level |
|---|---|
| `.env` or `.env.*` anywhere in the repo (skipping `.venv/`, `node_modules/`, `VSCodeExtension/runtime/`) | error, with a message giving the import command |
| `model_providers.json` present (after D10) | warn |
| `~/.gemini/.env` present (read by the gemini CLI; not ours to police) | warn |
| *(later)* DB file not set to permissions 600; DB backups containing secrets | warn |

The import action skips the `.env` check so you can migrate; `--delete-after` removes the file once it has been
imported.

### Cold start, import, export

- `env_import(conn, text, mode="merge"|"replace", dry_run=False) -> {added, changed, unchanged, removed}`.
- Sample: `examples/settings.example.env`, fictional values with no real keys (for example swiftlet on localhost
  and `CV_FAST_MODE=false`). Named so the audit pattern doesn't match it.
- Role CLI:
  - `--action settings-import --env-file F [--replace] [--delete-after]`
  - `--action settings-export [--reveal]` (secrets masked unless `--reveal` is given)
  - `--action settings-set --key K` (the value is read with `getpass` for secrets, or from stdin)
  - `--action settings-test --provider P`
- UI cold start: the first-run screen gets a Settings step: import (paste or upload a file, previewed as a diff),
  load the sample, or skip and configure by hand.
- Cold-start test: `--action backup`, delete the DB, start the server, go through first run, import, test a
  provider, then restore the backup.

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/settings` | Catalog grouped (Global, one group per backend, Other) with values. Secrets come back masked (`sk-…abcd`) with an `is_set` flag |
| `PUT /api/settings` | `{set: {K: V}, delete: [K]}` in one transaction. An unchanged masked placeholder is ignored |
| `POST /api/settings/reveal` | `{key}`: returns one secret in plain text, on demand |
| `GET /api/settings/env?reveal=0|1` | Simulated `.env` text, grouped and commented by section |
| `POST /api/settings/import` | `{text, mode, dry_run}`: returns the diff summary |
| `POST /api/settings/test` | `{provider, overrides?}`: runs the test against the saved settings plus unsaved form values |

Secrets never appear in `/api/state`. `EDITOR_FILES["env"]` and its file API are removed.

### Provider test

New optional backend member `test_connection(env) -> TestResult(ok, message, elapsed_seconds, model)`. The default
runs `interrogate`, then one `run_attempt` with "Reply with OK", the first model in `model_sequence`, a short timeout
and no fallback. A real call each time (D3).

### UI

A **Settings** panel (`cv_web/static/js/settings-feature.js`) replaces the Env tab:

- **Global:** default provider, fast mode, theme, font priority; an Advanced section that starts collapsed.
- **Providers:** one card per backend showing enabled/disabled with its `reason`, its declared fields (secrets as
  password inputs with Reveal), and **Test** and **Save** buttons. "Add provider" means picking a disabled backend
  and filling in its fields.
- **Other:** a key/value row editor for undeclared keys.
- **Import / Export:** Import (paste or file, previewed as a diff), Load sample, View as `.env` (masked, Reveal,
  Copy, Download).

