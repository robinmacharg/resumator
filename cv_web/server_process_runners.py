"""Subprocess execution and streaming helpers for CV/research workflows.

Architecture role:
- Layer: backend process execution utilities.
- Responsibility: run CV/research subprocesses, stream output, and finalize
  run-state snapshots without owning global state directly.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any


def run_research_format_for_active_run_streaming(deps: dict[str, Any]) -> int:
    """Run research PDF formatting for an active research run.

    Inputs:
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - Process exit code from the formatter invocation.
    """
    command = deps["_build_research_format_command"]()

    deps["append_current_research_output"]("Auto-formatting research PDF...\n")
    deps["append_current_research_output"](f"Formatting command: {' '.join(command)}\n")

    proc = subprocess.Popen(
        command,
        cwd=deps["ROOT_DIR"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    stdout_thread = threading.Thread(
        target=deps["stream_pipe_research"],
        args=(proc.stdout,),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=deps["stream_pipe_research"],
        args=(proc.stderr, "[stderr] "),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    return_code = proc.wait()
    stdout_thread.join()
    stderr_thread.join()
    return return_code


def stream_pipe(pipe, deps: dict[str, Any], prefix: str = "") -> None:
    """Stream process output lines into the current CV run buffer.

    Inputs:
    - pipe: Subprocess output stream.
    - deps: Dependency map supplied by cv_web.server.
    - prefix: Prefix for each streamed line.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        for line in iter(pipe.readline, ""):
            deps["append_current_run_output"](f"{prefix}{line}")
    finally:
        pipe.close()


def stream_pipe_research(pipe, deps: dict[str, Any], prefix: str = "") -> None:
    """Stream process output lines into the current research run buffer.

    Inputs:
    - pipe: Subprocess output stream.
    - deps: Dependency map supplied by cv_web.server.
    - prefix: Prefix for each streamed line.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        for line in iter(pipe.readline, ""):
            deps["append_current_research_output"](f"{prefix}{line}")
    finally:
        pipe.close()


def run_subprocess_streaming(
    kind: str,
    selected_provider: str,
    selected_model: str,
    deps: dict[str, Any],
    theme: str = "",
    steering_file: str | None = None,
) -> dict[str, Any]:
    """Run CV generation/format subprocess while streaming output.

    Inputs:
    - kind: Run kind, such as full or format.
    - selected_provider: Optional provider override.
    - selected_model: Optional model override.
    - deps: Dependency map supplied by cv_web.server.
    - theme: Optional PDF theme preset; empty string uses the default theme.
    - steering_file: Full runs only; None keeps generate_cv's default, "" disables steering.

    Returns:
    - Finalized run-state payload.
    """
    command = deps["make_command"](
        kind,
        selected_provider=selected_provider,
        selected_model=selected_model,
        theme=theme,
        steering_file=steering_file,
    )

    started_at = deps["utc_now_iso"]()
    started_monotonic = time.monotonic()
    deps["set_current_run"](
        deps["_build_run_state"](
            kind=kind,
            command=command,
            selected_provider=selected_provider,
            selected_model=selected_model,
            exit_code=None,
            started_at=started_at,
            finished_at=None,
            elapsed_seconds=0.0,
            success=None,
            running=True,
            output="",
            started_monotonic=started_monotonic,
        )
    )

    proc = subprocess.Popen(
        command,
        cwd=deps["ROOT_DIR"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stdout_thread = threading.Thread(
        target=deps["stream_pipe"],
        args=(proc.stdout,),
        kwargs={"deps": deps},
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=deps["stream_pipe"],
        args=(proc.stderr, "[stderr] "),
        kwargs={"deps": deps},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    return_code = proc.wait()
    stdout_thread.join()
    stderr_thread.join()

    run_result = deps["finalize_current_run"](return_code)
    if run_result is None:
        raise RuntimeError("Run completed but no run state was available.")

    return run_result


def run_subprocess_async(
    kind: str,
    selected_provider: str,
    selected_model: str,
    deps: dict[str, Any],
    theme: str = "",
    steering_file: str | None = None,
) -> None:
    """Run CV generation/format subprocess asynchronously.

    Inputs:
    - kind: Run kind, such as full or format.
    - selected_provider: Optional provider override.
    - selected_model: Optional model override.
    - deps: Dependency map supplied by cv_web.server.
    - theme: Optional PDF theme preset; empty string uses the default theme.
    - steering_file: Full runs only; None keeps generate_cv's default, "" disables steering.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        deps["run_subprocess_streaming"](
            kind,
            selected_provider=selected_provider,
            selected_model=selected_model,
            theme=theme,
            steering_file=steering_file,
        )
    except Exception as exc:
        deps["_finalize_run_error_state"](
            deps["_build_run_state"](
                kind=kind,
                command=deps["make_command"](
                    kind,
                    selected_provider=selected_provider,
                    selected_model=selected_model,
                    theme=theme,
                    steering_file=steering_file,
                ),
                selected_provider=selected_provider,
                selected_model=selected_model,
                exit_code=1,
                started_at=deps["utc_now_iso"](),
                finished_at=deps["utc_now_iso"](),
                elapsed_seconds=0.0,
                success=False,
                running=False,
                output=f"Wrapper failed to execute run: {exc}",
            )
        )
    finally:
        deps["RUN_LOCK"].release()


def run_research_subprocess_streaming(
    company_name: str,
    urls: list[str],
    dry_run: bool,
    auto_format_pdf: bool,
    selected_provider: str,
    selected_model: str,
    deps: dict[str, Any],
) -> dict[str, Any]:
    """Run research generation subprocess while streaming output.

    Inputs:
    - company_name: Company context for research prompt.
    - urls: URLs used as research sources.
    - dry_run: Whether to skip external model invocation.
    - auto_format_pdf: Whether to format PDF after successful research run.
    - selected_provider: Optional provider override.
    - selected_model: Optional model override.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - Finalized research run-state payload.
    """
    command = deps["_build_research_command"](
        company_name=company_name,
        urls=urls,
        dry_run=dry_run,
        selected_provider=selected_provider,
        selected_model=selected_model,
    )

    started_at = deps["utc_now_iso"]()
    started_monotonic = time.monotonic()
    deps["set_current_research_run"](
        deps["_build_research_run_state"](
            command=command,
            company_name=company_name,
            urls=urls,
            dry_run=dry_run,
            auto_format_pdf=auto_format_pdf,
            selected_provider=selected_provider,
            selected_model=selected_model,
            exit_code=None,
            started_at=started_at,
            finished_at=None,
            elapsed_seconds=0.0,
            success=None,
            running=True,
            output="",
            started_monotonic=started_monotonic,
        )
    )

    proc = subprocess.Popen(
        command,
        cwd=deps["ROOT_DIR"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    deps["set_current_research_proc"](proc)

    stdout_thread = threading.Thread(
        target=deps["stream_pipe_research"],
        args=(proc.stdout,),
        kwargs={"deps": deps},
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=deps["stream_pipe_research"],
        args=(proc.stderr, "[stderr] "),
        kwargs={"deps": deps},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        return_code = proc.wait()
        stdout_thread.join()
        stderr_thread.join()
    finally:
        deps["set_current_research_proc"](None)

    if return_code == 0 and not dry_run and auto_format_pdf:
        format_exit_code = deps["run_research_format_for_active_run_streaming"]()
        format_success = format_exit_code == 0
        deps["update_current_research_run_fields"](
            formatAttempted=True,
            formatSuccess=format_success,
            formatExitCode=format_exit_code,
        )
        if format_success:
            deps["append_current_research_output"]("Research PDF formatting complete.\n")
        else:
            deps["append_current_research_output"](
                "[stderr] Research succeeded, but PDF auto-format failed. "
                "Use Format Research PDF to retry.\n"
            )
    else:
        deps["update_current_research_run_fields"](
            formatAttempted=False,
            formatSuccess=None,
            formatExitCode=None,
        )

    run_result = deps["finalize_current_research_run"](return_code)
    if run_result is None:
        raise RuntimeError("Research run completed but no run state was available.")

    return run_result


def run_research_format_subprocess_streaming(deps: dict[str, Any]) -> dict[str, Any]:
    """Run research formatter subprocess while streaming output.

    Inputs:
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - Finalized research-format run-state payload.
    """
    command = deps["_build_research_format_command"]()

    started_at = deps["utc_now_iso"]()
    started_monotonic = time.monotonic()
    deps["set_current_research_run"](
        deps["_build_research_format_state"](
            command=command,
            exit_code=None,
            started_at=started_at,
            finished_at=None,
            elapsed_seconds=0.0,
            success=None,
            running=True,
            output="",
            started_monotonic=started_monotonic,
        )
    )

    proc = subprocess.Popen(
        command,
        cwd=deps["ROOT_DIR"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    deps["set_current_research_proc"](proc)

    stdout_thread = threading.Thread(
        target=deps["stream_pipe_research"],
        args=(proc.stdout,),
        kwargs={"deps": deps},
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=deps["stream_pipe_research"],
        args=(proc.stderr, "[stderr] "),
        kwargs={"deps": deps},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        return_code = proc.wait()
        stdout_thread.join()
        stderr_thread.join()
    finally:
        deps["set_current_research_proc"](None)

    run_result = deps["finalize_current_research_run"](return_code)
    if run_result is None:
        raise RuntimeError("Research format completed but no run state was available.")

    run_result["formattedPdfMtime"] = deps["file_mtime"](deps["RESEARCH_FORMATTED_PDF"])
    deps["LAST_RESEARCH_RUN"].clear()
    deps["LAST_RESEARCH_RUN"].update(run_result)
    return run_result


def run_research_subprocess_async(
    company_name: str,
    urls: list[str],
    dry_run: bool,
    auto_format_pdf: bool,
    selected_provider: str,
    selected_model: str,
    deps: dict[str, Any],
) -> None:
    """Run research generation subprocess asynchronously.

    Inputs:
    - company_name: Company context for research prompt.
    - urls: URLs used as research sources.
    - dry_run: Whether to skip external model invocation.
    - auto_format_pdf: Whether to format PDF after successful research run.
    - selected_provider: Optional provider override.
    - selected_model: Optional model override.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        deps["run_research_subprocess_streaming"](
            company_name=company_name,
            urls=urls,
            dry_run=dry_run,
            auto_format_pdf=auto_format_pdf,
            selected_provider=selected_provider,
            selected_model=selected_model,
        )
    except Exception as exc:
        deps["_finalize_research_run_error_state"](
            deps["_build_research_run_state"](
                command=deps["_build_research_command"](
                    company_name=company_name,
                    urls=urls,
                    dry_run=dry_run,
                    selected_provider=selected_provider,
                    selected_model=selected_model,
                ),
                company_name=company_name,
                urls=urls,
                dry_run=dry_run,
                auto_format_pdf=auto_format_pdf,
                selected_provider=selected_provider,
                selected_model=selected_model,
                exit_code=1,
                started_at=deps["utc_now_iso"](),
                finished_at=deps["utc_now_iso"](),
                elapsed_seconds=0.0,
                success=False,
                running=False,
                output=f"Wrapper failed to execute research run: {exc}",
            )
        )
    finally:
        deps["RESEARCH_RUN_LOCK"].release()


def run_research_format_subprocess_async(deps: dict[str, Any]) -> None:
    """Run research formatter subprocess asynchronously.

    Inputs:
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        deps["run_research_format_subprocess_streaming"]()
    except Exception as exc:
        deps["_finalize_research_run_error_state"](
            deps["_build_research_format_state"](
                command=deps["_build_research_format_command"](),
                exit_code=1,
                started_at=deps["utc_now_iso"](),
                finished_at=deps["utc_now_iso"](),
                elapsed_seconds=0.0,
                success=False,
                running=False,
                output=f"Wrapper failed to execute research format: {exc}",
            )
        )
    finally:
        deps["RESEARCH_RUN_LOCK"].release()
