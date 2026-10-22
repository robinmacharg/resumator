# Design: role research from the DB

## Decisions

| # | Decision | Why |
|---|---|---|
| RR1 | Research PDFs are rendered on demand from `research_run.output_md`, never stored; cached in `server_roles.RENDER_CACHE` | Same as CV runs (R6, R16) |
| RR2 | `research_format` gets text-in / bytes-out functions; the file CLI wraps them | One formatter for both modes; no `output/` writes in role mode |
| RR3 | Route `GET /api/roles/<id>/runs/research/<run>/research.pdf` | Mirrors `…/runs/cv/<run>/cv.<format>`. PDF only (research has no DOCX or theme) |
| RR4 | In role mode the Research tab shows the role's current research run; the Format button is hidden (the PDF is always current) | The run is the source of truth; formatting is now implicit |
| RR5 | Company and URLs prefill from the current research run (`company`, `urls_json`); no schema change | URLs aren't on the role; the last run is the natural default |
| RR6 | CLI: `research --out F` writes the run's PDF; `render --kind research` renders a stored research run | Parity with `cv --out` and `render` |

## Formatter

`research_format.format_markdown(text, heading)` → normalised markdown (today's `run` steps).
`research_format.render_research_pdf(text, heading, env)` → PDF bytes via pandoc (+ typst) in a temp dir; raises
`RuntimeError` with the reason (missing pandoc, empty input, pandoc failure).

## Frontend

The research preview kind in `pdf-preview-feature.js` takes a role run URL in role mode (as the CV preview does).
`research-feature.js` loads `GET /api/roles/<id>/runs` + `…/runs/research/<run>` for the current run after a run and
on role select. File mode is unchanged.
