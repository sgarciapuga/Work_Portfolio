# FX Prime Brokerage Collateral

This project generates synthetic FX prime brokerage collateral datasets for analysis, reporting, and dashboarding.

## What it does

The workflow builds a simple FX portfolio and derives collateral metrics from it. The main outputs are:

- a portfolio snapshot with trade-level and currency-level data
- a mark-to-market dataset for daily price movement exposure
- a collateral report showing initial margin, variation margin, collateral posted, and excess/deficit

## Project structure

```text
fx-prime-brokerage-collateral/
├── README.md
├── requirements.txt
├── data/
│   ├── FX-portfolio/
│   ├── Limits/
│   └── Mark-to-market/
└── src/
    ├── generate_fx_datasets.py
    ├── generate_fx_portfolio.py
    ├── generate_limits.py
    ├── generate_mark_to_market.py
    ├── generate_mtm_for_portfolio.py
    └── generate_mtm_report.py
```

## Main workflow

The entry point is the script in [fx-prime-brokerage-collateral/src/generate_fx_datasets.py](fx-prime-brokerage-collateral/src/generate_fx_datasets.py).

Run it from the repository root:

```bash
python fx-prime-brokerage-collateral/src/generate_fx_datasets.py
```

You can also write to a custom output directory:

```bash
python fx-prime-brokerage-collateral/src/generate_fx_datasets.py --out ./custom-output
```

## Generated outputs

The pipeline writes the following files:

- data/Limits/limits.csv
- data/Mark-to-market/mark_to_market_portfolio.csv
- data/Mark-to-market/mtm_report.csv
- data/FX-portfolio/portfolio.csv

## Dependencies

The project uses pandas and numpy. Install them with the repo-level requirements or the project-local requirements file.

## Notes

- The logic is intentionally synthetic and designed for examples and portfolio-style demonstrations.
- The collateral report uses sign conventions where positive values are favourable to the desk and negative values indicate a deficit.
