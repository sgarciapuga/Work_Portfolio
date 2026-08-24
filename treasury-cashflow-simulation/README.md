# Treasury Cashflow Simulation

This project simulates a small treasury's daily cash activity — account movements, internal sweeps, and resulting balances — for reporting and analytics demonstrations.

## Report

- [View the rendered report](../docs/treasury-cashflow-simulation/report.html)
- [Report source](report.qmd)

## What it does

The pipeline generates synthetic daily transactions (deposits, withdrawals, bank charges, month-end interest), applies internal sweep rules between accounts, and produces daily closing balances. Results are written to CSV and persisted to PostgreSQL for downstream reporting.

## Project structure

```text
treasury-cashflow-simulation/
├── README.md
├── requirements.txt
├── run_pipeline.py
├── report.qmd
├── data/
│   ├── Balances/
│   └── Movements/
├── src/
│   ├── load_static.py
│   ├── generate_movements.py
│   ├── sweep_engine.py
│   ├── balances_engine.py
│   └── simulate_pipeline.py
└── dashboard/
    └── treasury-cash-simulation.pbip
```

## Setup and run

Set `DATABASE_URL` in the repository `.env` file (repo root), then install dependencies:

```bash
pip install -r treasury-cashflow-simulation/requirements.txt
```

Run the pipeline from the repository root:

```bash
python treasury-cashflow-simulation/run_pipeline.py
```

## Outputs

- `treasury-cashflow-simulation/data/Balances/balances_YYYYMMDD.csv`
- `treasury-cashflow-simulation/data/Movements/movements_YYYYMMDD.csv`
- PostgreSQL tables: `treasury_balances`, `treasury_movements`

## Notes

The logic is intentionally synthetic and designed for portfolio-style demonstration, not as a production treasury cash-management engine.
