# Task 1: store `env_setting` table and functions

**Status:** done. **Read:** [design § Storage](../design.md#storage), D1.

## Do

- Migration 2 in `store.MIGRATIONS`: `env_setting(key, value, updated_at)`, key CHECK = env var name format.
- `store`: `list_env_settings`, `env_settings`, `get_env_setting`, `set_env_setting`, `delete_env_setting`,
  `replace_env_settings` (one transaction). Invalid keys raise `StoreError`.

## Done when

`tests/test_store.py` covers CRUD, separation from `setting`, `updated_at` only moving on change, replace, invalid
keys; the migration applies to a backup copy of the real DB.

## Handover

Built as above. `updated_at` is kept when a value is re-set unchanged (upsert `WHERE value IS NOT excluded.value`).
