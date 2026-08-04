# Resumator VS Code Bridge

A small VS Code extension that starts a local HTTP server and forwards prompt requests to Copilot through VS Code's language model API.

## Endpoints

- `GET /health`
- `POST /generate`

`/health` reports bridge process health and Copilot model readiness. Successful readiness includes:

- `modelReady: true`
- `status: "up"`

If `cvBridge.apiKey` is set in VS Code settings, both endpoints require:

- `x-api-key: <your key>`

Request body for `/generate`:

```json
{
  "prompt": "Write a tailored summary for this CV...",
  "systemPrompt": "Optional high-level instruction"
}
```

Response shape:

```json
{
  "ok": true,
  "output": "...model output..."
}
```

## Local Development

1. Open this folder in VS Code:
   - `/Users/rmacharg/dev/projects/Resumator/VSCodeExtension`
2. Install deps:
   - `npm install`
3. Compile:
   - `npm run compile`
4. Press `F5` to launch an Extension Development Host.
5. In the dev host, run command:
   - `CV Bridge: Start`

## Run From Main Boostworks Workspace (Multi-root)

If you want to run this from your usual Boostworks VS Code window (instead of opening only this folder), use this flow:

1. Ensure the CV extension folder is part of the workspace:
   - `/Users/rmacharg/dev/projects/Resumator/VSCodeExtension`
2. In that workspace, open Run and Debug.
3. Pick the configuration named `Run CV Bridge Extension`.
   - In multi-root, the dropdown can show folder-qualified names. Choose the one from the `VSCodeExtension` folder.
4. Press `F5`.
   - This opens an Extension Development Host window for the bridge extension.
5. In the Extension Development Host, run:
   - `CV Bridge: Start`
6. Test from your normal terminal:
   - `curl -s http://127.0.0.1:8766/health`

If VS Code prompts for unrelated extensions while pressing `F5`:
- Cancel/ignore the prompt for this flow.
- Re-check that the selected debug configuration is `Run CV Bridge Extension` from `VSCodeExtension`.

### Optional Fallback (no debug UI)

You can also launch an extension host directly from a terminal in the main workspace:

```bash
code --extensionDevelopmentPath /Users/rmacharg/dev/projects/Resumator/VSCodeExtension
```

Then run `CV Bridge: Start` in that opened window.

## Test

```bash
curl -s http://127.0.0.1:8766/health

curl -s -X POST http://127.0.0.1:8766/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Say hello in one line."}'
```

With API key enabled:

```bash
curl -s http://127.0.0.1:8766/health \
   -H 'x-api-key: your-local-key'

curl -s -X POST http://127.0.0.1:8766/generate \
   -H 'Content-Type: application/json' \
   -H 'x-api-key: your-local-key' \
   -d '{"prompt":"Say hello in one line."}'
```

## Resumator Integration

Use provider `vscodebridge` in CV scripts and configure these optional environment variables:

- `VSCODE_BRIDGE_API_URL` (default: `http://127.0.0.1:8766/generate`)
- `VSCODE_BRIDGE_API_KEY` (required only if extension `cvBridge.apiKey` is set)
- `VSCODE_BRIDGE_SYSTEM_PROMPT` (optional shared instruction)
- `VSCODE_BRIDGE_MODEL` (default: `copilot-vscode`)

Examples:

```bash
MODEL_PROVIDER=vscodebridge python3 generate_cv.py
MODEL_PROVIDER=vscodebridge python3 research_role.py
```

## Bridge Runtime Modes (Auto-start)

This folder includes scripts for running the bridge in two runtime modes:

- `start_isolated_bridge.sh`
- `stop_isolated_bridge.sh`

### Mode 1: Shared Auth (default)

Default behavior shares your main VS Code sign-in state so Copilot authentication is reused.

- Uses your existing VS Code account session.
- Launches the bridge in profile `CV Bridge` by default.
- Avoids writing bridge settings into your main global settings by passing runtime values via environment variables.

Optional variables for this mode:

- `CV_BRIDGE_RUNTIME_MODE=shared-auth` (default)
- `CV_BRIDGE_SHARE_MAIN_AUTH=true` (default; overrides mode when set)
- `CV_BRIDGE_PROFILE_NAME` (default `CV Bridge`)

### Mode 2: Fully Isolated

Use this when you want strict runtime separation and do not want to share main VS Code auth/session.

- `CV_BRIDGE_RUNTIME_MODE=isolated` or `CV_BRIDGE_SHARE_MAIN_AUTH=false`
- Uses dedicated directories:

- `VSCodeExtension/runtime/user-data` (isolated VS Code profile)
- `VSCodeExtension/runtime/extensions` (isolated extensions install)
- `VSCodeExtension/runtime/logs` (launcher logs)

In isolated mode, startup ensures `GitHub.copilot` is installed into the isolated extensions directory (unless `CV_BRIDGE_SKIP_EXTENSION_INSTALL=true`). `GitHub.copilot-chat` is provided as a built-in extension by VS Code.

When using the `vscodebridge` backend in Resumator, the backend can auto-start this isolated runtime if the bridge is not healthy.

Related environment variables:

- `BACKEND_VSCODEBRIDGE_ENABLED` (`true|false`, default `true`)
- `VSCODE_BRIDGE_API_URL` (default `http://127.0.0.1:8766/generate`)
- `VSCODE_BRIDGE_API_KEY` (optional, sent as `x-api-key`)
- `VSCODE_BRIDGE_AUTOSTART` (`true|false`, default `true`)
- `VSCODE_BRIDGE_STARTUP_TIMEOUT_SECONDS` (default `45`)
- `VSCODE_BRIDGE_STARTUP_CMD` (optional custom startup command override)
- `VSCODE_CLI_PATH` (optional explicit path to `code` CLI)
- `CV_BRIDGE_SKIP_EXTENSION_INSTALL` (`true|false`, default `false`)
- `CV_BRIDGE_RUNTIME_MODE` (`shared-auth|isolated`, default `shared-auth`)
- `CV_BRIDGE_SHARE_MAIN_AUTH` (`true|false`, default `true`; overrides runtime mode if set)
- `CV_BRIDGE_PROFILE_NAME` (shared-auth mode profile name, default `CV Bridge`)
- `CV_BRIDGE_REQUIRE_MODEL_READY` (`true|false`, default `true`; when true, launcher waits for `/health` to report `modelReady: true`)

Runtime state/logs are stored in `VSCodeExtension/runtime/`.

## End-to-End Test Steps

1. Kill existing CV server and old bridge listeners:

```bash
pkill -f '/Users/rmacharg/dev/projects/Resumator/cv_web/server.py' || true
./VSCodeExtension/stop_isolated_bridge.sh || true
```

2. Start bridge manually (shared-auth default, sanity check):

```bash
./VSCodeExtension/start_isolated_bridge.sh
curl -s http://127.0.0.1:8766/health
```

To force fully isolated mode:

```bash
CV_BRIDGE_RUNTIME_MODE=isolated ./VSCodeExtension/start_isolated_bridge.sh
```

3. Stop bridge again to validate auto-start path:

```bash
./VSCodeExtension/stop_isolated_bridge.sh
```

4. Start CV server with `vscodebridge` selected:

```bash
cd /Users/rmacharg/dev/projects/Resumator
MODEL_PROVIDER=vscodebridge python3 cv_web/server.py
```

5. In the web UI, run Full Pipeline or Research with provider set to VS Code Bridge.

6. Verify bridge auto-started and became healthy:

```bash
curl -s http://127.0.0.1:8766/health
```

7. Check bridge logs in `VSCodeExtension/runtime/logs/`.
8. Validate web restart flow:

```bash
curl -s -X POST http://127.0.0.1:8765/api/server/restart -H 'Content-Type: application/json' -d '{}'
```

9. Clean up:

```bash
./VSCodeExtension/stop_isolated_bridge.sh
pkill -f '/Users/rmacharg/dev/projects/Resumator/cv_web/server.py' || true
```

## Notes

- Requires a signed-in Copilot-enabled VS Code session.
- This is a stop-gap bridge and not an official CLI replacement.
- In shared-auth mode, Copilot sign-in is usually reused from your main VS Code instance.
- In isolated mode, first-run GitHub/Copilot sign-in prompts are expected.
