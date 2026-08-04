#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
USER_DATA_DIR="$RUNTIME_DIR/user-data"
EXTENSIONS_DIR="$RUNTIME_DIR/extensions"
LOG_DIR="$RUNTIME_DIR/logs"
SETTINGS_DIR="$USER_DATA_DIR/User"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"
PID_FILE="$RUNTIME_DIR/bridge.pid"

PORT="${CV_BRIDGE_PORT:-8766}"
API_KEY="${CV_BRIDGE_API_KEY:-}"
AUTO_START="${CV_BRIDGE_AUTOSTART:-true}"
STARTUP_TIMEOUT_SECONDS="${CV_BRIDGE_STARTUP_TIMEOUT_SECONDS:-60}"
CODE_BIN="${VSCODE_CLI_PATH:-}"
SKIP_EXTENSION_INSTALL="${CV_BRIDGE_SKIP_EXTENSION_INSTALL:-false}"
RUNTIME_MODE="${CV_BRIDGE_RUNTIME_MODE:-shared-auth}"
SHARE_MAIN_AUTH_RAW="${CV_BRIDGE_SHARE_MAIN_AUTH:-}"
PROFILE_NAME="${CV_BRIDGE_PROFILE_NAME:-CV Bridge}"
REQUIRE_MODEL_READY_RAW="${CV_BRIDGE_REQUIRE_MODEL_READY:-true}"

normalize_bool() {
  local raw="${1:-}"
  case "${raw:l}" in
    1|true|yes|on) return 0 ;;
    0|false|no|off) return 1 ;;
    *) return 2 ;;
  esac
}

USE_SHARED_AUTH=true
if [[ -n "$SHARE_MAIN_AUTH_RAW" ]]; then
  if normalize_bool "$SHARE_MAIN_AUTH_RAW"; then
    USE_SHARED_AUTH=true
  else
    parse_status=$?
    if [[ "$parse_status" -eq 1 ]]; then
      USE_SHARED_AUTH=false
    else
      echo "Invalid CV_BRIDGE_SHARE_MAIN_AUTH value: $SHARE_MAIN_AUTH_RAW" >&2
      exit 1
    fi
  fi
else
  case "${RUNTIME_MODE:l}" in
    shared|shared-auth|main-auth) USE_SHARED_AUTH=true ;;
    isolated|isolated-auth) USE_SHARED_AUTH=false ;;
    *)
      echo "Invalid CV_BRIDGE_RUNTIME_MODE value: $RUNTIME_MODE" >&2
      exit 1
      ;;
  esac
fi

REQUIRE_MODEL_READY=true
if normalize_bool "$REQUIRE_MODEL_READY_RAW"; then
  REQUIRE_MODEL_READY=true
else
  parse_status=$?
  if [[ "$parse_status" -eq 1 ]]; then
    REQUIRE_MODEL_READY=false
  else
    echo "Invalid CV_BRIDGE_REQUIRE_MODEL_READY value: $REQUIRE_MODEL_READY_RAW" >&2
    exit 1
  fi
fi

if [[ -z "$CODE_BIN" ]]; then
  CODE_BIN="$(command -v code || true)"
fi

if [[ -z "$CODE_BIN" ]]; then
  CODE_BIN="$(command -v code-insiders || true)"
fi

if [[ -z "$CODE_BIN" ]]; then
  echo "Unable to find VS Code CLI. Set VSCODE_CLI_PATH or install 'code' on PATH." >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

if [[ "$USE_SHARED_AUTH" == false ]]; then
  mkdir -p "$USER_DATA_DIR" "$EXTENSIONS_DIR" "$SETTINGS_DIR"
fi

if [[ ! -f "$SCRIPT_DIR/out/extension.js" ]]; then
  echo "Compiling extension (out/extension.js missing)..." >&2
  npm --prefix "$SCRIPT_DIR" run compile >/dev/null
fi

health_check() {
  local header_args=()
  if [[ -n "$API_KEY" ]]; then
    header_args=(-H "x-api-key: $API_KEY")
  fi
  local response body code
  response="$(curl -s -m 3 "${header_args[@]}" -w $'\n%{http_code}' "http://127.0.0.1:${PORT}/health" || true)"
  code="${response##*$'\n'}"
  body="${response%$'\n'*}"

  if [[ "$code" != "200" ]]; then
    return 1
  fi

  if [[ "$REQUIRE_MODEL_READY" == true ]]; then
    [[ "$body" =~ \"modelReady\"[[:space:]]*:[[:space:]]*true ]]
    return $?
  fi

  return 0
}

if health_check; then
  if [[ "$REQUIRE_MODEL_READY" == true ]]; then
    echo "Bridge already healthy and model-ready on port ${PORT}."
  else
    echo "Bridge already healthy on port ${PORT}."
  fi
  exit 0
fi

STALE_PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN | head -n 1 || true)"
if [[ -n "$STALE_PID" ]]; then
  echo "Bridge listener exists on port ${PORT} but is not ready; restarting it."
  "$SCRIPT_DIR/stop_isolated_bridge.sh" || true
fi

json_escape() {
  local input="$1"
  input="${input//\/\\}"
  input="${input//\"/\\\"}"
  input="${input//$'\n'/\\n}"
  printf '%s' "$input"
}

if [[ "$USE_SHARED_AUTH" == false ]]; then
  ESCAPED_KEY="$(json_escape "$API_KEY")"

  cat > "$SETTINGS_FILE" <<EOF
{
  "cvBridge.port": $PORT,
  "cvBridge.autoStart": ${AUTO_START:l},
  "cvBridge.apiKey": "$ESCAPED_KEY"
}
EOF
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && ! kill -0 "$OLD_PID" 2>/dev/null; then
    rm -f "$PID_FILE"
  fi
fi

if [[ "${SKIP_EXTENSION_INSTALL:l}" != "true" ]]; then
  if [[ "$USE_SHARED_AUTH" == true ]]; then
    echo "Shared-auth mode enabled; skipping extension install into isolated runtime dirs."
  else
    echo "Ensuring isolated runtime has required extensions..."

    install_extension_best_effort() {
      local extension_id="$1"
      if ! "$CODE_BIN" \
        --user-data-dir "$USER_DATA_DIR" \
        --extensions-dir "$EXTENSIONS_DIR" \
        --install-extension "$extension_id" \
        --force >/dev/null; then
        echo "Warning: unable to install ${extension_id} into isolated runtime; continuing." >&2
      fi
    }

    install_extension_best_effort "GitHub.copilot"
  fi
fi

LOG_FILE="$LOG_DIR/bridge-$(date +%Y%m%d-%H%M%S).log"

LAUNCH_ARGS=(
  --new-window
  --disable-workspace-trust
  --skip-welcome
)

if [[ "$USE_SHARED_AUTH" == true ]]; then
  LAUNCH_ARGS+=(--profile "$PROFILE_NAME")
else
  LAUNCH_ARGS+=(--user-data-dir "$USER_DATA_DIR" --extensions-dir "$EXTENSIONS_DIR")
fi

LAUNCH_ARGS+=(--extensionDevelopmentPath "$SCRIPT_DIR" "$SCRIPT_DIR")

nohup "$CODE_BIN" \
  "${LAUNCH_ARGS[@]}" \
  >"$LOG_FILE" 2>&1 &

LAUNCH_PID=$!
printf '%s\n' "$LAUNCH_PID" > "$PID_FILE"

if [[ "$USE_SHARED_AUTH" == true ]]; then
  echo "Shared-auth bridge launch requested (pid $LAUNCH_PID, profile '$PROFILE_NAME'). Logs: $LOG_FILE"
else
  echo "Isolated bridge launch requested (pid $LAUNCH_PID). Logs: $LOG_FILE"
fi

echo "Waiting for bridge health on port ${PORT}..."
deadline=$(( $(date +%s) + STARTUP_TIMEOUT_SECONDS ))
while (( $(date +%s) <= deadline )); do
  if health_check; then
    echo "Bridge is healthy on http://127.0.0.1:${PORT}/health"
    exit 0
  fi
  sleep 1
done

echo "Bridge did not become healthy within ${STARTUP_TIMEOUT_SECONDS}s."
echo "Inspect logs: $LOG_FILE"
exit 1
