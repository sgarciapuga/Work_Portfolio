# fx-prime-brokerage-collateral — dataset generators

This folder contains utilities to generate synthetic datasets used for the FX prime brokerage collateral examples.

Usage (from repository root):

```bash
# activate your Python env (uses pandas, numpy)
python fx-prime-brokerage-collateral/src/generate_fx_datasets.py
```

Outputs:
- `data/Limits/limits.csv` — per-counterparty limits snapshot
- `data/Mark-to-market/mark_to_market.csv` — trade-level MTM time series
- `data/Mark-to-market/mtm_report.csv` — daily collateral report with `collateral_required`, `collateral_posted`, and `excess_deficit`

Requirements are in `fx-prime-brokerage-collateral/requirements.txt`.
