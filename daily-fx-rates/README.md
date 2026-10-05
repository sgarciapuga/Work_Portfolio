# Daily FX Rates

This mini-project loads and stores daily FX rate history for a small treasury analytics workflow.

## Report

- [View the rendered report](../docs/daily-fx-rates/report.html)
- [Report source](report.qmd)
- [Presentation (PDF)](presentation/Daily-FX-Rates.pdf) / [PowerPoint](presentation/Daily-FX-Rates.pptx)
- [Live report (Google Data Studio)](https://datastudio.google.com/s/sC5tlwXPGVI)

The maintained implementation lives in [src/daily_fx_rates.py](src/daily_fx_rates.py).

## Project story

The presentation tells the project end to end. In short:

- **Why:** a proof of concept for building something real in Visual Studio Code with AI, and a way to get the FX rates my other reports need to convert data into USD.
- **How it runs:** GitHub Actions runs the script every day at 18:00 UTC (or by hand), saves the CSV backup back to GitHub, upserts into Neon PostgreSQL, and sends a Slack alert only if the run fails. A Google Data Studio report reads the table through SQL views and refreshes once a day, showing GBP/USD, EUR/USD and GBP/EUR.
- **Key decisions:** USD as the base currency; a rate for every day including weekends and holidays (`filled` vs `raw`); a database with the CSV as backup; a full check once a week instead of on every run.
- **Issues fixed:** missing days (weekly full check), duplicate rows (unique key on date and currency with upsert), and provisional values (filled rates from the last 7 days are rechecked on every run).
- **Working with AI:** I owned the idea, instructions, testing, debugging and the Data Studio report; AI (GitHub Copilot, now Claude) wrote the code from my instructions and helped solve each issue.
- **Why Data Studio:** anyone with the link can open it, whereas sharing Power BI needs a licence and admin rights.

## Purpose

The script fetches FX rates from the Frankfurter API and stores them in both:

- a local CSV backup file
- a Neon PostgreSQL table in the portfolio database

The workflow is designed to support historical backfill, daily incremental updates, and idempotent reruns.

## What it does

The script reads existing FX history, normalizes the keys, identifies missing business-day rows, retrieves the latest rates, and writes the result back out.

It has two run modes:

- **Daily run** (default): works only on the last 14 days. It loads that window from the database, gets the new rates, rechecks recently filled days, and upserts only those rows. The older part of the CSV is left as it is.
- **Full check**: reads the whole history from the database and the CSV, looks for missing business days since the start, rebuilds everything and upserts every row. It runs automatically every Monday, on the first run (no table or no CSV yet), and when the stored data does not cover the daily window (for example after the job was off for a while).

To force a full check at any time:

```bash
python daily-fx-rates/src/daily_fx_rates.py --full
```

or set the environment variable `FX_FULL_CHECK=1`.

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

## Project structure

```text
daily-fx-rates/
├── data/fx_rates.csv          # CSV backup, updated by the scheduled workflow
├── presentation/
│   ├── Daily-FX-Rates.pdf
│   └── Daily-FX-Rates.pptx
├── src/daily_fx_rates.py      # loader
├── report.qmd                 # Quarto report
├── requirements.txt
└── styles.css
```

The scheduled run is defined in `.github/workflows/daily_pipeline.yml`.

## Dependencies

The project relies on:

- pandas
- requests
- SQLAlchemy + PostgreSQL driver
- python-dotenv

## Notes

The loader now performs an idempotent upsert, keeps `fx_quality_flag` values in both CSV and Neon, and rechecks recently filled rows so provisional data can be promoted to raw once the source publishes it.

Failures stop the run instead of being hidden:

- If the Frankfurter API does not answer with status 200, the script raises an error and writes nothing. The GitHub Actions run fails and the Slack alert is sent.
- If the database cannot be reached or read, the script raises an error. Only a missing `fx_rates` table (first run) is treated as "no data yet".
