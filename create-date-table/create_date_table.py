import os
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, create_engine, text

# Load environment variables from .env in the repository root
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")

TABLE_NAME = "date_table"
KEY_COL = "calendar_date"
# Must cover the earliest date of every table with a foreign key to date_table
# (fx_rates and the treasury simulator backfill start on 1 Jan 2025).
START_DATE = date(2025, 1, 1)


def target_end_date(today: date | None = None) -> date:
    # Build ahead to the end of next year so downstream tables with a foreign
    # key to date_table (e.g. fx_rates) never write a date that is not there yet,
    # even when the scheduled runs are delayed or run out of order.
    today = today or date.today()
    return date(today.year + 1, 12, 31)


def build_date_table(start_date: date, end_date: date) -> pd.DataFrame:
    dates = pd.Series(pd.date_range(start=start_date, end=end_date, freq="D"))
    iso = dates.dt.isocalendar()
    df = pd.DataFrame({
        "calendar_date": dates.dt.date,
        "year": dates.dt.year,
        "quarter": dates.dt.quarter,
        "month": dates.dt.month,
        "month_name": dates.dt.month_name(),
        "day": dates.dt.day,
        "day_of_week": dates.dt.dayofweek + 1,  # ISO: Monday = 1 ... Sunday = 7
        "day_name": dates.dt.day_name(),
        "weekday": dates.dt.dayofweek,  # Monday = 0 ... Sunday = 6
        "is_weekend": dates.dt.dayofweek >= 5,
        "is_month_start": dates.dt.is_month_start,
        "is_month_end": dates.dt.is_month_end,
        # week_num is kept alongside iso_week because the Power BI dim_date uses it
        "week_num": iso["week"],
        "year_month": dates.dt.strftime("%Y-%m"),
        "year_quarter": dates.dt.year.astype(str) + "-Q" + dates.dt.quarter.astype(str),
        "iso_week": iso["week"],
        "iso_year": iso["year"],
    })
    int_cols = ["year", "quarter", "month", "day", "day_of_week", "weekday", "week_num", "iso_week", "iso_year"]
    df[int_cols] = df[int_cols].astype("int64")
    return df


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL missing from environment variables.")
    return database_url


def ensure_table_exists(engine):
    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            calendar_date DATE PRIMARY KEY,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            month INTEGER NOT NULL,
            month_name VARCHAR(20) NOT NULL,
            day INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            day_name VARCHAR(20) NOT NULL,
            weekday INTEGER NOT NULL,
            is_weekend BOOLEAN NOT NULL,
            is_month_start BOOLEAN NOT NULL,
            is_month_end BOOLEAN NOT NULL,
            week_num INTEGER NOT NULL,
            year_month VARCHAR(7) NOT NULL,
            year_quarter VARCHAR(8) NOT NULL,
            iso_week INTEGER NOT NULL,
            iso_year INTEGER NOT NULL
        )
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))


def upsert_dates(engine, df: pd.DataFrame) -> int:
    """Stage df in a TEMP table and upsert it into date_table on calendar_date.

    The column types come from date_table itself, not from pandas: psycopg 3
    (the driver of the CI DATABASE_URL) types every parameter, and Postgres
    will not cast between some of them. Rows that already hold the same values
    are left alone, so the return value counts only new or corrected dates.
    """
    staging = f"{TABLE_NAME}_staging"
    cols = list(df.columns)
    value_cols = [c for c in cols if c != KEY_COL]
    cols_sql = ", ".join(cols)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in value_cols)
    current = ", ".join(f"{TABLE_NAME}.{c}" for c in value_cols)
    incoming = ", ".join(f"EXCLUDED.{c}" for c in value_cols)

    with engine.begin() as conn:
        target = Table(TABLE_NAME, MetaData(), autoload_with=conn)
        dtype = {c.name: c.type for c in target.columns if c.name in cols}
        conn.execute(text(f"CREATE TEMP TABLE {staging} (LIKE {TABLE_NAME}) ON COMMIT DROP"))
        df.to_sql(staging, conn, if_exists="append", index=False, dtype=dtype)
        result = conn.execute(text(f"""
            INSERT INTO {TABLE_NAME} ({cols_sql})
            SELECT {cols_sql} FROM {staging}
            ON CONFLICT ({KEY_COL}) DO UPDATE SET {updates}
            WHERE ({current}) IS DISTINCT FROM ({incoming})
        """))
        return result.rowcount


def main():
    database_url = get_database_url()
    engine = create_engine(database_url)

    end_date = target_end_date()
    df_calendar = build_date_table(START_DATE, end_date)

    ensure_table_exists(engine)
    changed = upsert_dates(engine, df_calendar)

    if changed:
        print(f"Inserted or corrected {changed} rows in {TABLE_NAME}.")
    else:
        print(f"{TABLE_NAME} is already up to date.")
    print(f"Date table ready from {START_DATE} to {end_date}.")


if __name__ == "__main__":
    main()
