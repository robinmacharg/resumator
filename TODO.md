# Tasks to do for the Resumator project

- .env -> DB + UI (docs/plans/settings-in-db/index.md)

## Security

- DB backups (`store.backup`, `--action backup`) carry provider keys in plain text: exclude, redact or encrypt
  secrets in programmatic backups (and consider encrypting `env_setting` at rest)

## UI

- UI: Role rename
- UI: Status -> bottom
- UI: buttons to square, recolour, Bootstrap?
- UI: styling - bootstrap, shadcn for task types, ant design?
- UI: tree in LHS
- UI: Activity spinners
- UI: draggable role bar

- Multiple master CVs
- Support "suggested summary line" in CV for older roles
- Tauri wrapping + plan -> Rust backend
- Analyse typical workflows/user journeys to inform UI.
- Docs: dev doc split, ERD -> Main, user guide, sphinx?
- Split logs tab out
- UI: Move primary tabs to top alongside title
- Token optimisation
  - bulk generate
- Research: PDF generated on the fly
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

