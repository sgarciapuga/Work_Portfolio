# CLAUDE.md

Instructions for Claude Code in this repo. The Copilot versions live in `.github/`; this file adapts them.

## Working style

- Read whatever files you need to understand a task properly; no need to minimise reads or searches.
- Keep edits scoped to the request. Additive changes over broad refactors; match existing code style.
- Ask before: large refactors across multiple projects, spawning subagents, or long-running jobs (full renders with `-Execute`, full pipeline runs against the DB).
- Run targeted tests/checks for what you changed; run the full suite only if asked or if the change is cross-cutting.
- No git commits, pushes or branch changes unless explicitly asked. The CSVs under `*/data/` are auto-updated by scheduled workflows (`auto: ... [skip ci]` commits) — don't hand-edit them.

## Repo layout

Quarto website; each project folder has `report.qmd`, `styles.css`, README, own `requirements.txt` and code. Shared Python helpers in `utils/`, render helpers in `scripts/`, rendered site in `docs/` (generated — don't edit by hand). Shared theme: `styles/portfolio.css`. Secrets (`DATABASE_URL`) live in the root `.env`, never committed.

## Quarto rendering

- Never call `quarto render` / `quarto preview` directly, and don't use the VS Code Quarto Preview button (wrong env, hangs). Use:
  - `scripts/render_all_reports.ps1` (optionally `-Execute`, `-Reports ...`)
  - `scripts/render_in_env_quarto.ps1 -ReportPath <path> [-Execute]`
  - `scripts/preview_in_env_quarto.ps1 -ReportPath <path>`
- These activate the `env_quarto` conda env. If matplotlib crashes natively, set `MPLBACKEND=Agg` (see `docs-internal/ENV_HARDENING.md`).
- Adding a new report requires registering it in **both** `_quarto.yml` (`project.render` + navbar) **and** `$AllReports` in `scripts/render_all_reports.ps1`, plus a card in `index.qmd`.

## New data projects

Follow `docs-internal/REPEATABLE_DATA_PROJECT_PLAYBOOK.md`:
1. CSV generator + tests + project `requirements.txt` + README.
2. PostgreSQL persistence (keep CSVs unchanged): CREATE TABLE IF NOT EXISTS → dedupe legacy keys → CREATE UNIQUE INDEX IF NOT EXISTS → TEMP staging → INSERT ON CONFLICT DO UPDATE. Deps: sqlalchemy, psycopg2-binary, python-dotenv.
3. GitHub Action in `.github/workflows/` with schedule + workflow_dispatch, same setup as existing workflows.

Done = tests pass, script runs, re-running doesn't grow row counts unexpectedly, README and workflow updated.

## Power BI

`fx-prime-brokerage-collateral/dashboard/` is a PBIP project in PBIR format. Claude has no Power BI MCP connection; work on the files directly:
- Model: TMDL files in `.SemanticModel/definition/` (tables, measures/DAX, relationships).
- Report: `.Report/definition/pages/<id>/page.json` and `visuals/<id>/visual.json` — visuals can be added, edited, restyled, moved or removed. Keep JSON valid against the `$schema` in each file; new visuals need a unique folder name/`name`.
- Power BI Desktop must be closed while editing files (it overwrites them on save); the user reopens the `.pbip` to check. Claude can't see the rendered report, so describe what changed and ask the user to confirm visually.
- Measures/columns a visual references must exist in the model — check the TMDL before wiring a visual.

## Diagrams

Mermaid diagrams go in `.mmd` files (or ```mermaid blocks in `.qmd`). The Mermaid extension's validator/preview tools aren't available to Claude — check syntax carefully and tell the user to preview in VS Code.
