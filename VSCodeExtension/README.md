# CVGen VS Code Bridge

A small VS Code extension that starts a local HTTP server and forwards prompt requests to Copilot through VS Code's language model API.

## Endpoints

- `GET /health`
- `POST /generate`

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
   - `/Users/rmacharg/dev/projects/CVgen/VSCodeExtension`
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
   - `/Users/rmacharg/dev/projects/CVgen/VSCodeExtension`
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
code --extensionDevelopmentPath /Users/rmacharg/dev/projects/CVgen/VSCodeExtension
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

## CVgen Integration

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

## Notes

- Requires a signed-in Copilot-enabled VS Code session.
- This is a stop-gap bridge and not an official CLI replacement.
