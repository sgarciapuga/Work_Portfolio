# Professional Portfolio

A curated portfolio of professional projects and case studies demonstrating experience across treasury, financial data, analytics, business processes, and technology. The projects showcase practical problem-solving, data-driven analysis, and the ability to translate business requirements into clear, actionable solutions.

The portfolio is published as a Quarto website. The landing page is [index.qmd](index.qmd), and each project has its own narrative report (`report.qmd`) alongside its code or source material.

## Projects

| Project | Report source | Rendered report |
|---|---|---|
| Kyriba TMS Transformation | [kyriba-transformation/report.qmd](kyriba-transformation/report.qmd) | [docs/kyriba-transformation/report.html](docs/kyriba-transformation/report.html) |
| FX Prime Brokerage Collateral | [fx-prime-brokerage-collateral/report.qmd](fx-prime-brokerage-collateral/report.qmd) | [docs/fx-prime-brokerage-collateral/report.html](docs/fx-prime-brokerage-collateral/report.html) |
| Treasury Cashflow Simulation | [treasury-cashflow-simulation/report.qmd](treasury-cashflow-simulation/report.qmd) | [docs/treasury-cashflow-simulation/report.html](docs/treasury-cashflow-simulation/report.html) |
| Daily FX Rates | [daily-fx-rates/report.qmd](daily-fx-rates/report.qmd) | [docs/daily-fx-rates/report.html](docs/daily-fx-rates/report.html) |
| Create Date Table | [create-date-table/report.qmd](create-date-table/report.qmd) | [docs/create-date-table/report.html](docs/create-date-table/report.html) |

- **Kyriba TMS Transformation** — a source-traceable case study of Kyriba Treasury Management System functional design, data governance, integrations and continuous improvement, built from a supplied presentation. Includes a sub-project pattern (`kyriba-transformation/accounting/`) for deeper topic-specific pages.
- **FX Prime Brokerage Collateral** — a reproducible Python pipeline generating synthetic FX portfolio, limits, mark-to-market and collateral datasets, connected to a Power BI dashboard.
- **Treasury Cashflow Simulation** — synthetic daily cash movements, internal sweeps, and cash-position reporting persisted to PostgreSQL.
- **Daily FX Rates** — daily FX-rate ingestion from the Frankfurter API with historical backfill, data-quality flags, and PostgreSQL storage.
- **Create Date Table** — a reusable PostgreSQL calendar dimension for reporting and time intelligence.

Each project folder has its own README with setup and run instructions specific to that project.

## Repository structure

```text
Work_Portfolio/
├── README.md
├── _quarto.yml
├── index.qmd
├── styles/                      # shared portfolio-wide stylesheet
├── docs/                        # rendered Quarto website (output)
├── kyriba-transformation/
│   └── accounting/              # example sub-project page
├── fx-prime-brokerage-collateral/
├── treasury-cashflow-simulation/
├── daily-fx-rates/
├── create-date-table/
├── scripts/                     # Quarto render/preview helpers
└── utils/                       # shared Python helpers (dates, db, logging, paths)
```

## Getting started

1. Activate the project's Python environment (see each project's README for its own requirements file).
2. Install dependencies for the project you want to run, for example:

```bash
pip install -r treasury-cashflow-simulation/requirements.txt
```

3. Run the project's entry point, for example:

```bash
python treasury-cashflow-simulation/run_pipeline.py
```

Keep secrets such as `DATABASE_URL` in a local `.env` file at the repository root; they are not committed.

## Rendering the Quarto site

Do not call `quarto render` directly — always use the dedicated helper scripts, which activate the `env_quarto` conda environment and write output to `docs/`.

Render the whole site:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\render_all_reports.ps1
```

Render a single report (add `-Execute` to run code cells):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\render_in_env_quarto.ps1 -ReportPath "kyriba-transformation/report.qmd" -Execute
```

Live-preview a single report while editing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preview_in_env_quarto.ps1 -ReportPath "kyriba-transformation/report.qmd"
```

See [scripts/QUARTO_RENDERING.txt](scripts/QUARTO_RENDERING.txt) for the full reference.

## Adding a new project

1. Create a project folder with its own `report.qmd`, `styles.css`, README, and source code/data as needed.
2. Register the report in `_quarto.yml` under `project.render` and add a navbar entry (or a dropdown `menu` if it has sub-pages, following the `kyriba-transformation` pattern).
3. Add a card to [index.qmd](index.qmd) linking to the new report.
4. Render with `scripts/render_all_reports.ps1` to confirm the site builds cleanly.

## Notes

- The portfolio is designed to be expanded over time; new projects and sub-projects should follow the same pattern.
- The shared visual theme lives in [styles/portfolio.css](styles/portfolio.css) and is combined automatically with each project's own `styles.css`.

