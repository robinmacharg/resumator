# Task 6: settings API

**Status:** done. **Read:** [design § API](../design.md#api); `cv_web/static/ARCHITECTURE.md` (endpoint
ownership); how `server_roles.py` handlers are wired.

## Do

Endpoints `GET/PUT /api/settings`, `POST /api/settings/reveal`, `GET /api/settings/env`, `POST
/api/settings/import`, `POST /api/settings/test`. Unchanged masked placeholders are ignored on PUT. Secrets never in
`/api/state`.

## Done when

Server tests in the style of `tests/test_server_roles.py`, against a temp DB via `server_roles.DB_PATH`.

## Handover

- Handlers in `cv_web/server_settings.py`, routed through `server_roles.dispatch` (new `_PUT_ROUTES`); the server
  gained `do_PUT` and `server_http_handlers.dispatch_put`. Errors are `store.StoreError` (400).
- `GET /api/settings` → `{groups: [{id, label, settings: [{key, label, secret, default, kind, choices, help,
  advanced, isSet, value}]}]}`; PUT returns the same plus `success`. Test overrides: blank string unsets a key.
- Bug found and fixed: synthesized "Other" specs have `secret=False`, which hid the name heuristic;
  `settings_io.declared_specs` leaves them out (export had the same flaw).
- `EDITOR_FILES["env"]`, the `/api/save` env path and the frontend Env tab are still there: task 7 removes them.
- Secrets-not-in-`/api/state` is checked by a source test (state builders never read `env_settings`).
