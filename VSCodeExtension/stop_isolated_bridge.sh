#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
PID_FILE="$RUNTIME_DIR/bridge.pid"
PORT="${CV_BRIDGE_PORT:-8766}"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    sleep 0.5
    kill -KILL "$PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

PORT_PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN | head -n 1 || true)"
if [[ -n "$PORT_PID" ]]; then
  kill -TERM "$PORT_PID" 2>/dev/null || true
  sleep 0.3
  kill -KILL "$PORT_PID" 2>/dev/null || true
fi

sleep 0.2
POST_PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN | head -n 1 || true)"
if [[ -n "$POST_PID" ]]; then
  echo "Bridge stop attempted, but listener still present on port $PORT (pid $POST_PID)." >&2
  exit 1
fi

echo "Bridge stopped (or was not running)."
