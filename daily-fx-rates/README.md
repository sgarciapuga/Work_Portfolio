# Daily FX Rates

This mini-project loads and stores daily FX rate history for a small treasury analytics workflow.

## Report

- [View the rendered report](../docs/daily-fx-rates/report.html)
- [Report source](report.qmd)
- [Presentation (PDF)](presentation/Daily-FX-Rates.pdf) / [PowerPoint](presentation/Daily-FX-Rates.pptx)
- [Live report (Google Data Studio)](https://datastudio.google.com/s/sC5tlwXPGVI)
- [Streamlit version of the live report](app/streamlit_app.py) (see [Streamlit report](#streamlit-report))

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

## Streamlit report

[app/streamlit_app.py](app/streamlit_app.py) rebuilds the Data Studio report in Streamlit, with the same layout and the same numbers:

- KPI cards for GBP/USD, EUR/USD and GBP/EUR, with the change vs the previous market day and since the start of the period
- GBP and EUR against USD, rebased to 100 on the first day of the period
- GBP/EUR with its 30-day average and the period high and low
- a period summary table (latest, high, low, average, change since start)
- a date range picker that drives everything on the page

Definitions match Data Studio: "vs previous day" compares the last two market (`raw`) days, so it still shows a move on weekends; high, low and average use every calendar day in the period. The calculations live in [app/fx_metrics.py](app/fx_metrics.py) and are tested in [tests/test_fx_metrics.py](tests/test_fx_metrics.py).

Data comes from the `fx_rates` table when `DATABASE_URL` is set (Streamlit secrets, environment variable, or the root `.env`). If it is not set, or the database cannot be reached within 10 seconds, the app reads `data/fx_rates.csv`. The footer shows which source was used. Data is cached for an hour.

Run it from the repository root:

```bash
pip install -r daily-fx-rates/app/requirements.txt
streamlit run daily-fx-rates/app/streamlit_app.py
```

The app has its own `requirements.txt`, so the daily pipeline does not install Streamlit. To host it on Streamlit Community Cloud, point the app at `daily-fx-rates/app/streamlit_app.py` and add `DATABASE_URL` under the app's secrets. Without the secret it shows the CSV, which the daily workflow commits to GitHub.

Run the tests:

```bash
python -m unittest daily-fx-rates/tests/test_fx_metrics.py
```

## Project structure

```text
daily-fx-rates/
├── app/
│   ├── streamlit_app.py       # Streamlit report
│   ├── fx_metrics.py          # pair rates, KPIs, rebasing, moving average
│   └── requirements.txt       # Streamlit app dependencies
├── data/fx_rates.csv          # CSV backup, updated by the scheduled workflow
├── presentation/
│   ├── Daily-FX-Rates.pdf
│   └── Daily-FX-Rates.pptx
├── src/daily_fx_rates.py      # loader
├── tests/test_fx_metrics.py
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
