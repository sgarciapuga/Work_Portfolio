# Treasury Simulator

A day-by-day simulator of a central treasury entity that runs as the group's in-house bank. It covers the multi-currency balance sheet, daily cash positioning, MMF investments, intercompany loans and deposits, facility drawings, FX flattening and forecasts.

It is built as **one treasury engine with two group profiles**:

1. **Investment group** (first): an investment vehicle with capital calls and distributions, and service companies with fees, payroll and costs.
2. **Corporate group** (later): the same engine, with sales and purchase flows instead.

Each feature carries a **tier** (1 = I know this, 2 = easy to argue, 3 = I know the definition, 4 = good to know it exists). The tier sets how deeply the feature is built, and the app shows it as a badge.

The full design (decisions, tier map, balance sheet, daily cycle, data model, KPIs, phases) is in the project design doc.

## Status

Phase 1 (foundation) is done:

- static data for the made-up Aldmere Group
- the `tsim` schema for Neon
- an app with the page structure

Daily history starts in Phase 2.

| Phase | Content | Status |
|---|---|---|
| 1 | Static data, `tsim` schema, CHF in the FX feed, app skeleton | Done |
| 2 | Cash and balance sheet: daily engine, in-house bank settlement, MMF accruals, 2-year backfill | Next |
| 3 | Daily cash management: autopilot, IC loans and deposits, FX deals with MTM | |
| 4 | IV and facilities: calls and distributions, USD 50m buffer, drawings | |
| 5 | Forecasting: downside / base / upside, 13-week view, accuracy | |
| 6 | Scenarios, bank accounts, Learn page | |
| 7 | Corporate profile | |

## Project structure

```text
treasury-simulator/
├── README.md
├── requirements.txt
├── run_setup.py            # validate static data; create schema; load static data
├── static/                 # hand-written seed data (not pipeline outputs)
│   ├── entities.csv  banks.csv  accounts.csv  flow_codes.csv
│   ├── fee_schedule.csv  iv_commitments.csv  facilities.csv  mmf_funds.csv
│   └── glossary.csv        # Learn page, by tier
├── sql/tsim_schema.sql     # Neon schema (re-runnable)
├── src/tsim/
│   ├── config.py           # agreed settings (buffer, tolerance, margins, day counts)
│   ├── static_data.py      # load + validate the static CSVs
│   └── db.py               # create schema, upsert static data
├── app/                    # Streamlit app (8 pages)
└── tests/
```

## Key settings (`src/tsim/config.py`)

| Setting | Value |
|---|---|
| Base currency | USD (EUR, GBP, CHF against USD) |
| History start | 1 Jan 2025 |
| Operating cash on TRS accounts | USD 100k equivalent per currency |
| FX tolerance (net open position) | ± USD 50k equivalent per currency |
| IV buffer | USD 50m minimum deposit with TRS |
| IC loans / IC deposits | MMF rate + 50 bp / MMF rate − 10 bp |
| Facilities | Secured USD 300m (base + 150 bp), RCF USD 200m (base + 200 bp), commitment fee 35% of margin |

## Setup and run

From the repository root:

```bash
pip install -r treasury-simulator/requirements.txt

# Check the static data (no database needed)
python treasury-simulator/run_setup.py --check

# Create the tsim schema in Neon and load the static data (needs DATABASE_URL in the root .env)
python treasury-simulator/run_setup.py --schema --static

# Tests
python -m pytest treasury-simulator/tests

# App
pip install -r treasury-simulator/app/requirements.txt
streamlit run treasury-simulator/app/streamlit_app.py
```

FX rates come from the Daily FX Rates feed (`public.fx_rates`), shown in the schema as the view `tsim.fx_rate`.

## Notes

The group, banks and funds are made up. The data is synthetic and built for a portfolio demonstration, not for production use. Idea and design are mine; AI helped write the code.
