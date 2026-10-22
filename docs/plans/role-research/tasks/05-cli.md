# Task 5: role CLI research PDF

**Status:** todo. **Read:** RR6; `resumator.py` (`_cv`, `_research`, `_render`).

## Do

- `--action research --out F` writes the run's PDF.
- `--action render --kind research [--run N]` renders the current or given research run (default
  `output/<slug>-research<id>.pdf`); `--kind` defaults to `cv`.
- Tests in `tests/test_resumator_cli.py`.

## Done when

Both work on a DB copy; tests pass.

## Handover

