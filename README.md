# Resumator (CVgen)

Resumator is a local web tool that helps you tailor your CV to a role, run the generation pipeline, and preview outputs.

## What this project does

- Lets you edit source files in the browser:
  - input/CV.md
  - input/prompt.md
  - input/jobspec.txt
  - .env
- Runs CV generation or formatting from the UI.
- Shows live run progress and logs.
- Produces output files in output/, such as output/tailored.md, output/tailored_dev.pdf, and output/tailored_dev.docx.

## Prerequisites

- Python 3.10+
- Gemini CLI available on PATH (for full generation)
- A valid Gemini auth/session for your environment
- Optional but recommended for conversions:
  - pandoc
  - typst

## Install dependencies

### 1) Python environment

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

Note: current project scripts use Python standard-library modules only, so `requirements.txt` is intentionally minimal.

### 2) Gemini CLI (required for full CV generation)

Install globally with npm:

```bash
npm install -g @google/gemini-cli
```

Authenticate Gemini CLI in your shell/session before running full generation.

### 3) Conversion tools (optional but recommended)

If you want reliable PDF/DOCX conversion from markdown, install:

```bash
brew install pandoc typst
```

## Quick dependency check

```bash
python3 --version
gemini --version
pandoc --version
typst --version
```

If `pandoc` or `typst` are not installed, the app can still run, but output conversion behavior may be limited.

## Start the web server

From the project root:

```bash
python3 -m cv_web
```

You should see:

- `CV wrapper running on http://127.0.0.1:8765`

To stop the server, press Ctrl+C.

## Open the app

- Open this URL in your browser:
  - http://127.0.0.1:8765

## Typical usage

1. Open the editor tabs and update CV, prompt, job spec, or env values.
2. Click Save on the tabs you changed.
3. Click Run Full Pipeline to generate tailored output.
4. Watch progress in the Logs tab (Run Log updates in real time).
5. Review:
  - Tailored tab for output/tailored.md
  - PDF Preview pane for output/tailored_dev.pdf

## Output files

Generated files are written in output/, including:

- output/tailored.md
- output/tailored.model-output.txt
- output/tailored.model.json
- output/tailored.export.md
- output/tailored_dev.pdf
- output/tailored_dev.docx

## Troubleshooting

- If the page does not reflect recent code changes, restart the server.
- If generation fails, open Logs -> Debug Log and inspect the newest attempt log.
- If port 8765 is already in use, stop the existing process and start the server again.
