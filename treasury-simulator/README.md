# Treasury Simulator

A day-by-day simulator of a central treasury entity that runs as the group's in-house bank. It covers the multi-currency balance sheet, daily cash positioning, MMF investments, intercompany loans and deposits, facility drawings, FX flattening and forecasts.

It is built as **one treasury engine with two group profiles**:

1. **Investment group** (first): an investment vehicle with capital calls and distributions, and service companies with fees, payroll and costs.
2. **Corporate group** (later): the same engine, with sales and purchase flows instead.

Each feature carries a **tier** (1 = I know this, 2 = easy to argue, 3 = I know the definition, 4 = good to know it exists). The tier sets how deeply the feature is built, and the app shows it as a badge.

The full design (decisions, tier map, balance sheet, daily cycle, data model, KPIs, phases) is in the project design doc.

## Status

Phase 1 (foundation) is done and Phase 2 (cash and balance sheet) is built:

- static data for the made-up Aldmere Group, the `tsim` schema for Neon, and an app with the page structure
- a daily engine that rebuilds the history from 1 Jan 2025:
  - scheduled group flows (with small, reproducible variation)
  - zero-balancing of every entity sub-account against TRS, booked on IC current accounts
  - MMF / deposit investing above the USD 100k operating minimum, with interest paid on BD2
  - IC interest (MMF + 50 bp / MMF − 10 bp), posted at month end
  - the TRS balance sheet and NAV per currency and in USD
- real overnight rates (SOFR, €STR, SONIA, SARON), downloaded daily
- live Overview and Balance sheet & NAV pages
- Phase 2.1: a Market data page (FX in market convention, overnight rates, rate differentials, implied 1M / 3M forwards)

| Phase | Content | Status |
|---|---|---|
| 1 | Static data, `tsim` schema, CHF in the FX feed, app skeleton | Done |
| 2 | Cash and balance sheet: daily engine, in-house bank settlement, MMF accruals, 2-year backfill | Built |
| 2.1 | Market data page: FX rates, overnight rates, differentials, implied forwards | Built |
| 3 | Daily cash management: autopilot, IC loans and deposits, FX deals with MTM | Next |
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
├── run_daily.py            # daily engine: rebuild history, write CSVs, store in Neon
├── data/                   # engine outputs and overnight rates (CSV backups, updated by the workflow)
├── static/                 # hand-written seed data (not pipeline outputs)
│   ├── entities.csv  banks.csv  accounts.csv  flow_codes.csv
│   ├── fee_schedule.csv  iv_commitments.csv  facilities.csv  mmf_funds.csv
│   └── glossary.csv        # Learn page, by tier
├── sql/tsim_schema.sql     # Neon schema (re-runnable)
├── src/tsim/
│   ├── config.py           # agreed settings (buffer, tolerance, margins, day counts)
│   ├── static_data.py      # load + validate the static CSVs
│   ├── calendars.py        # business days per currency (US, TARGET, England, Zurich)
│   ├── schedule.py         # fee and cost schedules -> dated flows
│   ├── rates.py            # SOFR, €STR, SONIA, SARON download; MMF and IC rates
│   ├── market.py           # FX in market convention, implied forwards, differentials
│   ├── engine.py           # the daily engine
│   └── db.py               # schema, static data, engine outputs in Neon
├── app/                    # Streamlit app (9 pages)
└── tests/                  # what each file checks: tests/README.md
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

# Daily engine: download overnight rates, rebuild the history, write CSVs to treasury-simulator/data/
python treasury-simulator/run_daily.py --fetch-rates

# ...and store it in Neon (the whole history with --full; otherwise the last 14 days)
python treasury-simulator/run_daily.py --fetch-rates --db --full

# Tests
python -m pytest treasury-simulator/tests

# App
pip install -r treasury-simulator/app/requirements.txt
streamlit run treasury-simulator/app/streamlit_app.py
```

The workflow `.github/workflows/treasury_simulator_7pm.yml` runs every day at 19:00 UTC (after the FX feed). It runs the tests, creates or updates the schema, runs the engine with fresh rates, stores the results in Neon (the whole history on Mondays) and commits the CSV backups.

[tests/README.md](tests/README.md) lists what each test file checks.

FX rates come from the Daily FX Rates feed (`public.fx_rates`), shown in the schema as the view `tsim.fx_rate`.

## Notes

The group, banks and funds are made up. The data is synthetic and built for a portfolio demonstration, not for production use. Idea and design are mine; AI helped write the code.
