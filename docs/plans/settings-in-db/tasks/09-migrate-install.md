# Task 9: migrate this install and cold-start test

**Status:** todo. **Read:** D2, D7; AGENTS.md invariants on the real DB and `.env`.

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

(fill in at the end of the task)
