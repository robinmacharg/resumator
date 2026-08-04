"""
Architecture role:
- Layer: backend runtime state store and mutators.
- Responsibility: own in-memory run/research state, snapshots, process handles,
  and stop/finalization transitions.

Plain-language purpose:
- This module keeps mutable runtime state out of the HTTP routing module so server
  handlers can stay focused on orchestration and response shaping.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output"
RESEARCH_FORMATTED_PDF = OUTPUT_DIR / "research_output.formatted.pdf"

RUN_STATE_LOCK = threading.Lock()
LAST_RUN: dict[str, Any] = {}
CURRENT_RUN: dict[str, Any] = {}

RESEARCH_STATE_LOCK = threading.Lock()
LAST_RESEARCH_RUN: dict[str, Any] = {}
CURRENT_RESEARCH_RUN: dict[str, Any] = {}

RESEARCH_PROC_LOCK = threading.Lock()
CURRENT_RESEARCH_PROC: subprocess.Popen[str] | None = None


def _utc_now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _file_mtime(path: Path) -> float | None:
    """Return file mtime when path exists; otherwise None."""
    if not path.exists():
        return None
    return path.stat().st_mtime


def get_current_run_snapshot() -> dict[str, Any] | None:
    """Return current CV run snapshot with computed elapsed time when running."""
    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return None

        snapshot = {
            key: value
            for key, value in CURRENT_RUN.items()
            if not key.startswith("_")
        }

        started_monotonic = CURRENT_RUN.get("_startedMonotonic")
        if isinstance(started_monotonic, float) and snapshot.get("running"):
            snapshot["elapsedSeconds"] = round(time.monotonic() - started_monotonic, 2)

        return snapshot


def set_current_run(run_state: dict[str, Any]) -> None:
    """Replace current CV run state with the provided payload."""
    with RUN_STATE_LOCK:
        CURRENT_RUN.clear()
        CURRENT_RUN.update(run_state)


def append_current_run_output(chunk: str) -> None:
    """Append output text to the current CV run buffer."""
    if not chunk:
        return

    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return

        existing = CURRENT_RUN.get("output", "")
        CURRENT_RUN["output"] = existing + chunk


def finalize_current_run(return_code: int) -> dict[str, Any] | None:
    """Finalize current CV run and publish immutable last-run snapshot."""
    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return None

        started_monotonic = CURRENT_RUN.get("_startedMonotonic")
        elapsed = round(time.monotonic() - started_monotonic, 2) if isinstance(started_monotonic, float) else 0.0

        CURRENT_RUN["running"] = False
        CURRENT_RUN["exitCode"] = return_code
        CURRENT_RUN["finishedAt"] = _utc_now_iso()
        CURRENT_RUN["elapsedSeconds"] = elapsed
        CURRENT_RUN["success"] = return_code == 0
        CURRENT_RUN["pdfMtime"] = _file_mtime(OUTPUT_DIR / "tailored_dev.pdf")
        CURRENT_RUN["docxMtime"] = _file_mtime(OUTPUT_DIR / "tailored_dev.docx")

        snapshot = {
            key: value
            for key, value in CURRENT_RUN.items()
            if not key.startswith("_")
        }
        CURRENT_RUN.clear()

    LAST_RUN.clear()
    LAST_RUN.update(snapshot)
    return snapshot


def get_current_research_run_snapshot() -> dict[str, Any] | None:
    """Return current research run snapshot with computed elapsed time when running."""
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return None

        snapshot = {
            key: value
            for key, value in CURRENT_RESEARCH_RUN.items()
            if not key.startswith("_")
        }

        started_monotonic = CURRENT_RESEARCH_RUN.get("_startedMonotonic")
        if isinstance(started_monotonic, float) and snapshot.get("running"):
            snapshot["elapsedSeconds"] = round(time.monotonic() - started_monotonic, 2)

        return snapshot


def set_current_research_run(run_state: dict[str, Any]) -> None:
    """Replace current research run state with the provided payload."""
    with RESEARCH_STATE_LOCK:
        CURRENT_RESEARCH_RUN.clear()
        CURRENT_RESEARCH_RUN.update(run_state)


def set_current_research_proc(proc: subprocess.Popen[str] | None) -> None:
    """Set pointer to currently running research subprocess."""
    with RESEARCH_PROC_LOCK:
        global CURRENT_RESEARCH_PROC
        CURRENT_RESEARCH_PROC = proc


def get_current_research_proc() -> subprocess.Popen[str] | None:
    """Get pointer to currently running research subprocess."""
    with RESEARCH_PROC_LOCK:
        return CURRENT_RESEARCH_PROC


def append_current_research_output(chunk: str) -> None:
    """Append output text to the current research run buffer."""
    if not chunk:
        return

    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return

        existing = CURRENT_RESEARCH_RUN.get("output", "")
        CURRENT_RESEARCH_RUN["output"] = existing + chunk


def update_current_research_run_fields(**fields: Any) -> None:
    """Update selected keys in current research run state."""
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return
        CURRENT_RESEARCH_RUN.update(fields)


def finalize_current_research_run(return_code: int) -> dict[str, Any] | None:
    """Finalize current research run and publish immutable last-run snapshot."""
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return None

        started_monotonic = CURRENT_RESEARCH_RUN.get("_startedMonotonic")
        elapsed = round(time.monotonic() - started_monotonic, 2) if isinstance(started_monotonic, float) else 0.0

        CURRENT_RESEARCH_RUN["running"] = False
        CURRENT_RESEARCH_RUN["exitCode"] = return_code
        CURRENT_RESEARCH_RUN["finishedAt"] = _utc_now_iso()
        CURRENT_RESEARCH_RUN["elapsedSeconds"] = elapsed
        CURRENT_RESEARCH_RUN["success"] = return_code == 0
        CURRENT_RESEARCH_RUN["stoppedByUser"] = bool(CURRENT_RESEARCH_RUN.get("stopRequested", False))
        CURRENT_RESEARCH_RUN["formattedPdfMtime"] = _file_mtime(RESEARCH_FORMATTED_PDF)

        snapshot = {
            key: value
            for key, value in CURRENT_RESEARCH_RUN.items()
            if not key.startswith("_")
        }
        CURRENT_RESEARCH_RUN.clear()

    LAST_RESEARCH_RUN.clear()
    LAST_RESEARCH_RUN.update(snapshot)
    return snapshot


def _finalize_run_error_state(run_state: dict[str, Any]) -> None:
    """Publish a failed CV run payload as last-run state and clear current state."""
    set_current_run(run_state)
    snapshot = get_current_run_snapshot()
    if snapshot is not None:
        LAST_RUN.clear()
        LAST_RUN.update(snapshot)
        with RUN_STATE_LOCK:
            CURRENT_RUN.clear()


def _finalize_research_run_error_state(run_state: dict[str, Any]) -> None:
    """Publish a failed research payload as last-run state and clear current state."""
    set_current_research_run(run_state)
    snapshot = get_current_research_run_snapshot()
    if snapshot is not None:
        LAST_RESEARCH_RUN.clear()
        LAST_RESEARCH_RUN.update(snapshot)
        with RESEARCH_STATE_LOCK:
            CURRENT_RESEARCH_RUN.clear()


def request_stop_research_run() -> bool:
    """Set stop flag and terminate active research process when present."""
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN or not CURRENT_RESEARCH_RUN.get("running"):
            return False
        CURRENT_RESEARCH_RUN["stopRequested"] = True

    proc = get_current_research_proc()
    if proc is None:
        return False

    append_current_research_output("Stop requested by user. Terminating research process...\n")

    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return False

    return True
