# Daily FX Rates

This mini-project loads and stores daily FX rate history for a small treasury analytics workflow.

The maintained implementation lives in [src/daily_fx_rates.py](src/daily_fx_rates.py).

## Purpose

The script fetches FX rates from the Frankfurter API and stores them in both:

- a local CSV backup file
- a Neon PostgreSQL table in the portfolio database

The workflow is designed to support historical backfill, daily incremental updates, and idempotent reruns.

## What it does

The script reads existing FX history from the database and CSV file, normalizes the keys, identifies missing business-day rows, retrieves the latest rates, and writes a consolidated dataset back out.

It currently covers:

- USD as the base currency
- EUR and GBP as target currencies
- a quality flag so filled rows can be tracked and revalidated later
- a database-level unique key on date and currency to prevent duplicates

## Entry point

The current loader logic is implemented in [src/daily_fx_rates.py](src/daily_fx_rates.py).

## Outputs

The workflow writes to:

- daily-fx-rates/data/fx_rates.csv
- Neon PostgreSQL (table: fx_rates)

## Dependencies

The project relies on:

- pandas
- requests
- SQLAlchemy + PostgreSQL driver
- python-dotenv

## Notes

The loader now performs an idempotent upsert, keeps `fx_quality_flag` values in both CSV and Neon, and rechecks recently filled rows so provisional data can be promoted to raw once the source publishes it.
