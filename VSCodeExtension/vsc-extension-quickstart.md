This extension was scaffolded manually for a local HTTP bridge use case.

Quick run options:

1. Standalone folder run:
	- Open `/Users/rmacharg/dev/projects/CVgen/VSCodeExtension`
	- `npm install`
	- `npm run compile`
	- Press `F5` (config: `Run CV Bridge Extension`)

2. Main Boostworks multi-root run:
	- Keep using your main workspace window
	- Ensure `/Users/rmacharg/dev/projects/CVgen/VSCodeExtension` is included as a workspace folder
	- In Run and Debug, select `Run CV Bridge Extension` from the `VSCodeExtension` folder
	- Press `F5`

In the Extension Development Host window, run command `CV Bridge: Start`.
Then test with:

```bash
curl -s http://127.0.0.1:8766/health

curl -s -X POST http://127.0.0.1:8766/generate \
	-H 'Content-Type: application/json' \
	-d '{"prompt":"Reply with exactly: bridge-ok"}'
```

If you set `cvBridge.apiKey`, include the header in both requests:

```bash
curl -s http://127.0.0.1:8766/health \
	-H 'x-api-key: your-local-key'
```

For full details, see `README.md`.
