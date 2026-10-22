# Task 9: migrate this install and cold-start test

**Status:** done. **Read:** D2, D7; AGENTS.md invariants on the real DB and `.env`.

## Do

With the user present: `--action backup`; `--action settings-import --env-file .env --delete-after` on the real DB
(the user's explicit go-ahead first); confirm providers enabled. Then a cold-start rehearsal on a copy: delete,
start, first run, import the backup's settings, test a provider. Never echo key values.

Moving the DB aside: stop the server **and** close the DB in any SQLite viewer (the VS Code one holds
`resumator.db-shm` open) first, and move `resumator.db` together with its `-wal`/`-shm`, or better, take a copy
with `--action backup` and delete the three files. A stale `-shm` next to a new DB gives `disk I/O error` on
`PRAGMA journal_mode = WAL` (seen in the task 8 manual check), and a `-wal` left behind loses its changes.

## Done when

No `.env` in the repo; the startup audit is clean; the user has confirmed the providers work.

## Handover

- Found state: `.env` moved by the user to `~/dev/.env` (outside the repo); live `resumator.db` was the task 8
  cold-start scratch DB, the real one sat beside it as `resumator.db.bak_tmp` (schema v1). Restored it (scratch DB
  backed up to the session scratchpad first, stale `-shm` dropped); migration 2 applied on first CLI open.
- `--action backup`, then `settings-import --env-file ~/dev/.env` (merge, 22 keys added; not `--delete-after`, so
  the file stays outside the repo for the user to delete). Startup audit clean.
- Provider tests: Gemini OK. Hugging Face and OpenAI fail on account credit, Swiftlet's server isn't running; the
  user accepts these. Gotcha: with another app on port 8080 (VLC), Swiftlet's 404 reads as "Check SWIFTLET_API_URL
  path".
- Cold-start rehearsal on a scratch DB: `setup --choice example`, `settings-export --reveal > file` (export writes
  to stdout; `--out` is a cv/render flag), `settings-import --delete-after`, Gemini test OK.
- Not done: the browser look at the Settings pop-over and first-run step (tasks 7–8 Handover) — still for the user.
