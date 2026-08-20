# Professional Portfolio

A curated portfolio of professional projects and case studies demonstrating experience across treasury, financial data, analytics, business processes, and technology. The projects showcase practical problem-solving, data-driven analysis, and the ability to translate business requirements into clear, actionable solutions.

## Portfolio overview

### Projects

- Treasury cashflow simulation
  - Simulates daily account movements, month-end interest, bank charges, deposits, withdrawals, and internal sweeps.
  - Stores results in CSV files and PostgreSQL tables for downstream reporting.

- FX prime brokerage collateral
  - Generates synthetic FX portfolio and collateral metrics such as initial margin, variation margin, and collateral surplus/deficit.
  - Produces collateral reports that are suitable for analysis and dashboarding.

- Daily FX rates
  - Loads daily FX rates from the Frankfurter API into a local CSV backup and Neon PostgreSQL table.
  - Supports historical backfill, incremental updates, idempotent reruns, and a `fx_quality_flag` for raw versus filled rows.

- Create date table
  - Builds and maintains a reusable calendar dimension table in PostgreSQL for reporting and date-based analytics.

## Repository structure

```text
Work_Portfolio/
├── README.md
├── create-date-table/
├── daily-fx-rates/
├── fx-prime-brokerage-collateral/
├── treasury-cashflow-simulation/
└── utils/
```

## Getting started

1. Create or activate a Python environment.
2. Install dependencies for the project you want to run. For example, Treasury Cashflow:

```bash
pip install -r treasury-cashflow-simulation/requirements.txt
```

3. Run the projects you need:

```bash
python treasury-cashflow-simulation/run_pipeline.py
```

For the individual mini-projects, use their own entry points as documented in their subfolders.

## Documentation

Each project folder includes:

- a GitHub-friendly README
- a Quarto report for narrative documentation and project walkthroughs

## Recommended workflow

- Use the repository root as the working directory for shared scripts.
- Keep environment variables such as DATABASE_URL in a local .env file.
- Render Quarto documents from the repo root when you want a polished HTML report.

### Render reports with the dedicated Quarto environment

If you want a simple way to render Quarto reports without switching environments manually, use the helper script in the scripts folder.

From PowerShell:

```powershell
pwsh -File .\scripts\render_report.ps1 -ReportPath "treasury-cashflow-simulation/report.qmd" -Execute
```

You can render any other report by changing the report path, for example:

```powershell
pwsh -File .\scripts\render_report.ps1 -ReportPath "treasury-cashflow-simulation-full-doc.qmd" -Execute
```

The script uses a dedicated conda environment named quarto_render and sets the Quarto Python executable automatically.

If you have not created that environment yet, run:

```powershell
& "C:\Users\44784\miniconda3\shell\condabin\conda-hook.ps1"
conda create -n quarto_render python=3.11 -y
conda activate quarto_render
conda install -c conda-forge jupyter ipykernel matplotlib pandas pyarrow -y
```

## Notes

- The portfolio is designed to be expanded over time.
- New projects should follow the same pattern: a README, clear entry-point scripts, and an accompanying report or notebook for explanation.
