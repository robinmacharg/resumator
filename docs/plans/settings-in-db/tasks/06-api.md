# Task 6: settings API

**Status:** todo. **Read:** [design § API](../design.md#api); `cv_web/static/ARCHITECTURE.md` (endpoint
ownership); how `server_roles.py` handlers are wired.

## Do

Endpoints `GET/PUT /api/settings`, `POST /api/settings/reveal`, `GET /api/settings/env`, `POST
/api/settings/import`, `POST /api/settings/test`. Unchanged masked placeholders are ignored on PUT. Secrets never in
`/api/state`.

## Done when

Server tests in the style of `tests/test_server_roles.py`, against a temp DB via `server_roles.DB_PATH`.

## Handover

(fill in at the end of the task)
