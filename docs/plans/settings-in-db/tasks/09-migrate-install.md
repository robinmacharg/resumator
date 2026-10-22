# Task 9: migrate this install and cold-start test

**Status:** todo. **Read:** D2, D7; AGENTS.md invariants on the real DB and `.env`.

## Do

With the user present: `--action backup`; `--action settings-import --env-file .env --delete-after` on the real DB
(the user's explicit go-ahead first); confirm providers enabled. Then a cold-start rehearsal on a copy: delete,
start, first run, import the backup's settings, test a provider. Never echo key values.

## Done when

No `.env` in the repo; the startup audit is clean; the user has confirmed the providers work.

## Handover

(fill in at the end of the task)
