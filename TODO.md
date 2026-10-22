# Tasks to do for the Resumator project

## Security

- DB backups (`store.backup`, `--action backup`) carry provider keys in plain text: exclude, redact or encrypt
  secrets in programmatic backups (and consider encrypting `env_setting` at rest)

## Machine housekeeping (not this repo)

- Python tidy-up (audited 2026-10-22; Homebrew python@3.12–3.15 all present as deps, all outdated):
    - `brew upgrade` Python formulae + dependents, then `brew autoremove --dry-run` to drop orphaned Pythons
    - Decide on `python-tk@3.12` and `wxpython` (only explicit installs; they pin 3.12/3.13)
    - `pipx reinstall-all` (poetry venv is on python@3.13)
    - Delete dead `/opt/homebrew/bin/protoc-gen-{grpclib_python,python_grpc}` (shebang → missing python@3.11)
    - De-dupe PATH: pipx `~/.local/bin` line is in both `~/.zprofile` and `~/.zshrc`; move `brew shellenv` to top of
      `~/.zprofile`

## UI

- UI: buttons to square, recolour, Bootstrap?
- UI: styling - bootstrap, shadcn for task types, ant design?
- UI: tree in LHS
- UI: Activity spinners

- Multiple master CVs
- Support "suggested summary line" in CV for older roles
- Tauri wrapping + plan -> Rust backend
- Analyse typical workflows/user journeys to inform UI.
- Docs: dev doc split, ERD -> Main, user guide, sphinx?
- Split logs tab out
- UI: Move primary tabs to top alongside title
- Token optimisation
    - bulk generate
- Scaling it up:
    - External hosting
    - multi-user
    - Auth architecture
- docs: How to read + package.json command to open, (and to generate PDF?)
- remove ALL file-based activity except example
- Business plan
    - 50p/CV gen
    - buy blocks? minimise friction?
- Stats on dashboard
- Application notes
    - Contacts
    - Per-application timeline
    - All points towards a CRM. Common CRM ER patterns?
- Top-level grouping?
    - Role
    - Company
    - "Application"
    - All three as projections of the data
- "ATS-friendly" -> re-evaluate/regenerate prompt(s) (auto LLM evaluation?)
    - Any public API for scoring?
