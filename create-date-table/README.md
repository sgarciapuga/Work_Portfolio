# Create Date Table

This folder contains a reusable script to build and populate a shared PostgreSQL `date_table`.

The table covers every date from `2026-01-01` through today and includes standard calendar attributes.

## Table fields

- `calendar_date`
- `year`
- `quarter`
- `month`
- `month_name`
- `day`
- `day_of_week`
- `day_name`
- `weekday`
- `is_weekend`
- `is_month_start`
- `is_month_end`
- `week_num`
- `year_month`
- `year_quarter`
- `iso_week`
- `iso_year`

## Usage

From the repository root, run:

```bash
python create-date-table/create_date_table.py
```

This script uses `DATABASE_URL` from the repository `.env` file to connect to PostgreSQL.

## GitHub Actions

The script is intended to be run automatically in CI just like the `daily-fx-rates` project.
A GitHub Action should:

1. check out the repository
2. install Python dependencies from `requirements.txt`
3. run `python create-date-table/create_date_table.py`

This repository now includes a matching workflow at `.github/workflows/create_date_table.yml`.
The action is configured to use the same `DATABASE_URL` secret used by `daily-fx-rates`.
