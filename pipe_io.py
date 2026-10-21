"""`--io json` harness shared by generate_cv.py and research_role.py (multi-role R14).

One JSON request on stdin, progress on stderr, one JSON result on stdout, no data files. While the handler runs,
fd 1 points at stderr, so every print (and any child process that inherits stdout) lands in the log and can't
corrupt the result. The result goes to a private copy of the original stdout.
"""

import json
import os
import sys
import traceback
from typing import Callable


class RequestError(ValueError):
    """The request is missing a field or has one of the wrong type."""


def require_text(request: dict, key: str, *, allow_empty: bool = False) -> str:
    """The string field `key` of the request; raises RequestError when missing, not a string or (by default) blank."""
    value = request.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise RequestError(f"request field '{key}' must be a non-empty string")
    return value


def optional_text(request: dict, key: str) -> str:
    """The string field `key`, or "" when absent or null; raises RequestError for other types."""
    value = request.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RequestError(f"request field '{key}' must be a string")
    return value


def run_json_io(handler: Callable[[dict], dict]) -> int:
    """Read the request, run handler(request) with stdout sent to stderr, write its result; return the exit code.

    The handler returns a result dict with `success` and `error`. A bad request or an exception becomes a result
    with `success: false` and the error, so the caller always gets one JSON object.
    """
    sys.stdout.flush()
    result_stream = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    result: dict = {"success": False, "error": "the run was aborted"}
    try:
        request = json.loads(sys.stdin.read())
        if not isinstance(request, dict):
            raise RequestError("the request must be a JSON object")
        result = handler(request)
    except (json.JSONDecodeError, RequestError) as exc:
        result = {"success": False, "error": f"invalid request: {exc}"}
    except Exception as exc:  # noqa: BLE001 - every failure must still produce a result
        traceback.print_exc(file=sys.stderr)
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        sys.stdout.flush()
        json.dump(result, result_stream, ensure_ascii=False)
        result_stream.write("\n")
        result_stream.close()
    return 0 if result.get("success") else 1
