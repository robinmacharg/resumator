# Resumator

A local web tool that tailors a master CV to a job spec with an LLM and renders the result as PDF and DOCX. It also
generates role research and interview prep notes. Each job application is a **role** with its own CV copy, job
spec, steering and run history, kept in a local SQLite database (`cv_web/resumator.db`, not in git). You can choose
between several LLM backends: Claude Code CLI, Gemini CLI, OpenAI, Hugging Face, a local Swiftlet server, or Copilot
via a VS Code bridge.

**Docs:** [architecture](docs/architecture.md) · [LLM backends](docs/backends.md) ·
[CV formats](docs/cv-format.md) · [gaps & roadmap](docs/gaps.md) · [frontend](cv_web/static/ARCHITECTURE.md) ·
[VS Code bridge](VSCodeExtension/README.md). For AI agents, start at [AGENTS.md](AGENTS.md).

## Prerequisites

- Python 3.11+ (standard library only, so `pip install` is not needed)
- `pandoc` and `typst` for PDF/DOCX output: `brew install pandoc typst`
- At least one backend, configured in the app's **Settings** (header cog; see [docs/backends.md](docs/backends.md)):
  - Claude Code: the `claude` CLI, logged in (`claude auth`)
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

1. First run: choose **Example data** (a sample CV, role and finished run to look around) or a **Blank master CV**,
   then import your settings (paste or upload a `.env`-style file, or load the sample) or skip and fill them in.
2. Fill in the master CV (the full record of your career; format: [cv-source-format](docs/cv-source-format.md)).
3. Add a role with **+** in the sidebar: name, company and the job spec. Its CV starts as a copy of the master;
   edit it freely (for example to leave something out). **Pull from master** / **Promote to master** merge changes
   either way, entry by entry, and **History** restores older versions.
4. Pick a provider and model, then **Run Full Pipeline**. Progress streams to Logs → Run Log. Every run is kept:
   the Run picker chooses which one the PDF preview and Tailored tab show, in the selected theme.
5. Research tab: run research for the selected role's company.

Role-mode CLI: `python3 -m resumator --action list|create|cv|research|render|…`. The one-shot scripts
(`generate_cv.py`, `research_role.py`) still work on `input/` and `output/` files; they read only their
settings from the database. Settings from the CLI: `--action settings-import|settings-export|settings-set|settings-test`. Both are in
[AGENTS.md](AGENTS.md#commands-repo-root). An install from before roles moves its files in once with
`python3 -m resumator --action migrate-single-role --role "Name"`.

## Troubleshooting

- Generation failed: read Logs → Run Log while it runs. A role run's log and raw model text are also saved with the
  run (`GET /api/roles/<id>/runs/cv/<run>`; the UI doesn't show past logs yet). One-shot runs leave a debug log per
  attempt in Logs → Debug Log and the raw model text in `output/tailored.model-output.txt`.
- "Failed JSON contract validation": the model output broke the schema in
  [docs/cv-format.md](docs/cv-format.md#3-model-json-contract). Try another model.
- Provider greyed out: hover over it to see the reason (usually a missing key; set it in Settings and use **Test**).
- "error: … .env found: config now lives in the settings DB": import it once (this also deletes it) with
  `python3 -m resumator --action settings-import --env-file .env --delete-after`.
- Code changes not showing: restart the server. If port 8765 is busy, stop the old process.
- Back up the database before risky changes: `python3 -m resumator --action backup` (copies to `cv_web/backups/`).
