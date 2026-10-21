# Resumator

A local web tool that tailors a master CV to a job spec with an LLM and renders the result as PDF and DOCX. It also
generates role research and interview prep notes. You can choose between several LLM backends: Gemini CLI, OpenAI,
Hugging Face, a local Swiftlet server, or Copilot via a VS Code bridge.

**Docs:** [architecture](docs/architecture.md) · [LLM backends](docs/backends.md) ·
[CV formats](docs/cv-format.md) · [gaps & roadmap](docs/gaps.md) · [frontend](cv_web/static/ARCHITECTURE.md) ·
[VS Code bridge](VSCodeExtension/README.md). For AI agents, start at [AGENTS.md](AGENTS.md).

## Prerequisites

- Python 3.10+ (standard library only, so `pip install` is not needed)
- `pandoc` and `typst` for PDF/DOCX output: `brew install pandoc typst`
- At least one backend, configured in `.env` (see [docs/backends.md](docs/backends.md)):
  - Gemini: `npm install -g @google/gemini-cli`, authenticated in your shell
  - OpenAI: `OPENAI_API_KEY` · Hugging Face: `HF_API_TOKEN` · Swiftlet: a local server at `SWIFTLET_API_URL`
  - VS Code bridge: see [VSCodeExtension/README.md](VSCodeExtension/README.md)

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional
```

## Run

```bash
python3 -m cv_web        # → http://127.0.0.1:8765  (Ctrl+C to stop)
```

1. Edit the CV, CV Prompt, Job Spec and `.env` in the tabs, then save.
2. Pick a provider and model, then **Run Full Pipeline**. Progress streams to Logs → Run Log.
3. Review the Tailored tab (`output/tailored.md`) and the PDF preview (`output/tailored_dev.pdf`).
4. Research tab: enter the company name and URLs, then run, then format to PDF.

CLI equivalents are in [AGENTS.md](AGENTS.md#commands-repo-root).

## Troubleshooting

- Generation failed: open Logs → Debug Log for the newest attempt. The raw model text is in
  `output/tailored.model-output.txt`.
- "Failed JSON contract validation": the model output broke the schema in
  [docs/cv-format.md](docs/cv-format.md#3-model-json-contract). Try another model.
- Provider greyed out: hover over it to see the reason (usually a missing key in `.env`).
- Code changes not showing: restart the server. If port 8765 is busy, stop the old process.
