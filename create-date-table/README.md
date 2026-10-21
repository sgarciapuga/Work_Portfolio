# Create Date Table

This mini-project builds and maintains a reusable calendar dimension table for analytics and reporting pipelines.

## Report

- [View the rendered report](../docs/create-date-table/report.html)
- [Report source](report.qmd)

## What it does

The script creates a PostgreSQL table called date_table with one row per calendar day. It includes common business-calendar attributes such as month, quarter, weekday, ISO week, and month start/end flags.

## Table structure

The generated table contains the following columns:

- calendar_date
- year
- quarter
- month
- month_name
- day
- day_of_week
- day_name
- weekday
- is_weekend
- is_month_start
- is_month_end
- week_num
- year_month
- year_quarter
- iso_week
- iso_year

## How it works

The workflow is implemented in [create_date_table.py](create_date_table.py):

1. It reads DATABASE_URL from the repository .env file.
2. It creates the date_table table if it does not already exist (`CREATE TABLE IF NOT EXISTS`).
3. It generates a date range from 2025-01-01 through 31 December of next year, so tables that reference date_table (for example fx_rates through its foreign key) always find today's date.
4. It stages the rows in a temporary table and upserts them on `calendar_date` (`INSERT ... ON CONFLICT DO UPDATE`). New dates are inserted, rows whose values changed are corrected, and identical rows are left alone, so re-running never adds duplicates.

[check_table_state.py](check_table_state.py) then verifies the table: it fails if the table is empty, starts after 2025-01-01, ends before 31 December of next year, or has gaps. [export_date_table.py](export_date_table.py) writes the table to [data/date_table.csv](data/date_table.csv).

## Usage

Run it from the repository root:

```bash
python create-date-table/create_date_table.py
python create-date-table/check_table_state.py
```

Run the tests (no database needed):

```bash
python -m unittest discover -s create-date-table/tests -v
```

## Dependencies

The script requires:

- pandas
- python-dotenv
- sqlalchemy
- psycopg2-binary

## CI and automation

The project is designed to be scheduled or invoked in CI. The workflow can:

1. check out the repository
2. install the Python dependencies
3. run the unit tests
4. run the script with the DATABASE_URL secret configured in GitHub Actions
5. verify the table, export it to CSV and commit the CSV if it changed

## Notes

This is a reusable building block for downstream reporting, data marts, and dashboard refreshes.
