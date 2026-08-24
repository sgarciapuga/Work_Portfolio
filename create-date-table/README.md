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

The workflow is implemented in [create-date-table/create_date_table.py](create-date-table/create_date_table.py):

1. It reads DATABASE_URL from the repository .env file.
2. It creates the date_table table if it does not already exist.
3. It generates a date range from 2026-01-01 through today.
4. It inserts only the missing dates, making the script suitable for incremental runs.

## Usage

Run it from the repository root:

```bash
python create-date-table/create_date_table.py
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
3. run the script with the DATABASE_URL secret configured in GitHub Actions

## Notes

This is a reusable building block for downstream reporting, data marts, and dashboard refreshes.
