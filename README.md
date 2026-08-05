# Treasury Cashflow Simulation

This repository contains a Python-based treasury cashflow simulation.
It generates synthetic daily transactions, applies internal sweeps, updates account balances, and persists results into a SQLite database.

## Quick start

1. Activate your Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the simulation:

```bash
python run_pipeline.py
```

## Quarto showcase

Render the project report with:

```bash
quarto render treasury-cashflow-simulation.qmd
```

## What is included

- `run_pipeline.py` — lightweight CLI entrypoint
- `treasury-cashflow-simulation/src/` — simulation package
- `utils/` — shared utilities
- `treasury-cashflow-simulation/data/` — generated CSV outputs and setup file
- `portfolio-data/treasury.db` — persisted simulation results

## Output files

After running `python run_pipeline.py`, the following outputs are generated:

- `treasury-cashflow-simulation/data/Balances/` — daily balance CSV files named `balances_YYYYMMDD.csv`
- `treasury-cashflow-simulation/data/Movements/` — daily movement CSV files named `movements_YYYYMMDD.csv`
- `portfolio-data/treasury.db` — SQLite database containing `balances` and `movements` tables

## Notes

- Run from the repository root so the paths resolve correctly.
- The Quarto document is designed to present the simulation results as a project showcase.
