# Plans: layout and session policy

Applies to every plan from `settings-in-db/` on. Older single-file plans (`multi-role*.md`, `cv-format-revamp.md`)
predate it and stay as they are.

## Layout

One folder per plan, `docs/plans/<plan-name>/`:

| File | Holds | Read |
|---|---|---|
| `index.md` | Goal, status, task table (links + status), session hints, Handoff, the continue prompt | Every session |
| `design.md` | Numbered decisions (D1…) and design sections | Only the sections the current task links |
| `tasks/NN-<name>.md` | One task: status, what to read, what to do, done-when, and its Handover notes | Only the current task |
| `log.md` | One dated entry per task or decision round, newest last | Only the last few entries |

Keep files terse: tables and bullets; name functions, not line numbers. A task file links design sections rather
than repeating them. Decisions are cited by number.

## End of every task

1. Set the task's status (task file and index table) and fill in its Handover.
2. Append a log entry; update the index Handoff (what's next, branch, uncommitted state, gotchas).
3. Tell the user whether to **start a new session** or **stay**, with a one-line reason:
   - **New session** when the context is past about half full, the task loaded a lot the next one won't need,
     the next task works on different files, or a group of tasks has just finished. Reloading the index, one task
     file and the log tail costs less than carrying a full context.
   - **Stay** when the context is still small and the next task mainly uses files already read or written.
4. When suggesting a new session, give the continue prompt from the plan's index.

The same applies to work outside a plan: at the end of a session, suggest a fresh one (with a short handover
prompt) when the next piece of work doesn't need what's in the current context.
