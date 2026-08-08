# Daily FX Rates

This mini-project loads and stores daily FX rate history for a small treasury analytics workflow.

## Purpose

The script fetches FX rates from the Frankfurter API and stores them in both:

- a local CSV backup file
- a SQLite table in the portfolio database

The workflow is designed to support historical backfill and daily incremental updates.

## What it does

The script reads existing FX history from the database and CSV file, identifies any missing dates, retrieves the latest rates, and writes a consolidated dataset back out.

It currently covers:

- USD as the base currency
- EUR and GBP as target currencies
- forward-filled values to keep the dataset complete for reporting

## Entry point

The logic is implemented in the R Markdown document [daily-fx-rates/daily_fx_rates.Rmd](daily-fx-rates/daily_fx_rates.Rmd) and the embedded Python code block inside it.

## Outputs

The workflow writes to:

- daily-fx-rates/data/fx_rates.csv
- portfolio-data/treasury.db (table: fx_rates)

## Dependencies

The project relies on:

- pandas
- requests
- sqlite3 (standard library)

## Notes

This project is a lightweight data ingestion example that can be extended with more currencies, additional sources, or scheduled automation.
