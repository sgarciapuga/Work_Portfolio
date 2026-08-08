# Work Portfolio

This repository collects a set of treasury, data engineering, and analytics projects that work together as a practical portfolio of financial-data workflows.

## Portfolio overview

### Projects

- Treasury cashflow simulation
  - Simulates daily account movements, month-end interest, bank charges, deposits, withdrawals, and internal sweeps.
  - Stores results in CSV files and a SQLite database for downstream reporting.

- FX prime brokerage collateral
  - Generates synthetic FX portfolio and collateral metrics such as initial margin, variation margin, and collateral surplus/deficit.
  - Produces collateral reports that are suitable for analysis and dashboarding.

- Daily FX rates
  - Loads daily FX rates from the Frankfurter API into a local CSV and SQLite dataset.
  - Supports historical backfill and incremental updates.

- Create date table
  - Builds and maintains a reusable calendar dimension table in PostgreSQL for reporting and date-based analytics.

## Repository structure

```text
Work_Portfolio/
├── README.md
├── run_pipeline.py
├── requirements.txt
├── create-date-table/
├── daily-fx-rates/
├── fx-prime-brokerage-collateral/
├── treasury-cashflow-simulation/
├── portfolio-data/
└── utils/
```

## Getting started

1. Create or activate a Python environment.
2. Install dependencies from the repository root:

```bash
pip install -r requirements.txt
```

3. Run the projects you need:

```bash
python run_pipeline.py
```

For the individual mini-projects, use their own entry points as documented in their subfolders.

## Documentation

Each project folder includes:

- a GitHub-friendly README
- a Quarto or R Markdown report for narrative documentation and project walkthroughs

## Recommended workflow

- Use the repository root as the working directory for shared scripts.
- Keep environment variables such as DATABASE_URL in a local .env file.
- Render Quarto documents from the repo root when you want a polished HTML report.

## Notes

- The portfolio is designed to be expanded over time.
- New projects should follow the same pattern: a README, clear entry-point scripts, and an accompanying report or notebook for explanation.
