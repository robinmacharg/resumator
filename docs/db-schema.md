# Database schema

The SQLite DB (`cv_web/resumator.db`) is defined only by the append-only `store.MIGRATIONS` in
[cv_web/store.py](../cv_web/store.py). **Keep this page in step with it:** any change to a migration list entry
updates the diagram and the table below in the same change (see "Doc upkeep" in [AGENTS.md](../AGENTS.md)).
Design background: [plans/multi-role-design.md](plans/multi-role-design.md) (roles, R1–R21) and
[plans/settings-in-db/design.md](plans/settings-in-db/design.md) (settings, D1–D11).

**Schema version:** 2 (migrations: 1 = roles, CVs, runs, `setting`; 2 = `env_setting`).

## ER diagram

```mermaid
erDiagram
    role ||--o{ cv_version : "owns (role_id)"
    cv_version |o--o{ cv_version : "parent_id"
    cv_version |o--o{ cv_version : "base_master_id (master row)"
    role ||--o{ cv_run : has
    role ||--o{ research_run : has
    cv_version ||--o{ cv_run : "input to"
    prompt_version ||--o{ cv_run : "prompt_hash"
    prompt_version ||--o{ research_run : "prompt_hash"
    schema_version {
        int version PK
        text applied_at
    }

    role {
        int id PK
        text slug UK
        text name
        text company
        text status "draft | applied | closed"
        text jobspec
        text steering_text
        int steering_enabled
        text theme
        text created_at
        text updated_at
    }
    cv_version {
        int id PK
        int role_id FK "NULL = master"
        int parent_id FK
        int base_master_id FK
        text source "seed | edit | promote | pull | import | example"
        text note
        text content
        text created_at
    }
    prompt_version {
        text hash PK
        text kind "cv | research"
        text content
        text created_at
    }
    cv_run {
        int id PK
        int role_id FK
        int cv_version_id FK
        text prompt_hash FK
        text provider
        text model
        text theme
        text steering_text
        text raw_output
        text model_json
        text warnings_json
        int page_count
        text log
        int success
        int is_current
        text started_at
        text finished_at
    }
    research_run {
        int id PK
        int role_id FK
        text prompt_hash FK
        text provider
        text model
        text company
        text urls_json
        int dry_run
        text output_json
        text output_md
        text log
        int success
        int is_current
        text started_at
        text finished_at
    }
    setting {
        text key PK
        text value "internal app state"
    }
    env_setting {
        text key PK "env var name, e.g. OPENAI_API_KEY"
        text value "plain text (D2)"
        text updated_at
    }
```

`schema_version` stands alone (one row per applied migration) and is shown in the diagram only for completeness.

## Tables

| Table | Holds | Notes |
|---|---|---|
| `schema_version` | Applied migrations | Written by `store.migrate` |
| `role` | One job application | `slug` unique; `status` draft/applied/closed (archive = closed, R21) |
| `cv_version` | Every saved CV text, master and per role | `role_id` NULL = master (R8); `parent_id` chains versions; `base_master_id` is the merge ancestor |
| `prompt_version` | Prompt templates by SHA-256 | Runs reference them by hash (R15) |
| `cv_run`, `research_run` | One pipeline run each, failures included | At most one `is_current` per role (partial unique index); `*_json` columns are `json_valid` checked |
| `setting` | Internal app state | `first_run_done`, `role_merge` import base, ... Not user config |
| `env_setting` | User config: the keys that used to live in `.env` | Key format CHECK; secrets are plain text for now (D2). Catalog and meaning of keys live in code (`settings_catalog.py`) |

Rules enforced in code rather than SQL: a role's `base_master_id` points at a master row; a CV run's
`cv_version_id` belongs to the same role. Connections: autocommit, `foreign_keys = ON`, WAL, `busy_timeout` 5 s.
