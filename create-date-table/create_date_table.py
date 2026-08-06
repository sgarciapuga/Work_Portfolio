import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Date, Boolean, Integer, String, create_engine, inspect, text

# Load environment variables from .env in the repository root
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")

TABLE_NAME = "date_table"
START_DATE = date(2026, 1, 1)


def build_date_table(start_date: date, end_date: date) -> pd.DataFrame:
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    df = pd.DataFrame({"calendar_date": dates})
    df["calendar_date"] = df["calendar_date"].dt.date
    df["year"] = df["calendar_date"].apply(lambda d: d.year)
    df["quarter"] = df["calendar_date"].apply(lambda d: (d.month - 1) // 3 + 1)
    df["month"] = df["calendar_date"].apply(lambda d: d.month)
    df["month_name"] = df["calendar_date"].apply(lambda d: d.strftime("%B"))
    df["day"] = df["calendar_date"].apply(lambda d: d.day)
    df["day_of_week"] = df["calendar_date"].apply(lambda d: d.isoweekday())
    df["day_name"] = df["calendar_date"].apply(lambda d: d.strftime("%A"))
    df["weekday"] = df["calendar_date"].apply(lambda d: d.weekday())
    df["is_weekend"] = df["weekday"].apply(lambda w: w >= 5)
    df["is_month_start"] = df["calendar_date"].apply(lambda d: d.day == 1)
    df["is_month_end"] = df["calendar_date"].apply(lambda d: (d + timedelta(days=1)).month != d.month)
    df["week_num"] = df["calendar_date"].apply(lambda d: d.isocalendar()[1])
    df["year_month"] = df["calendar_date"].apply(lambda d: d.strftime("%Y-%m"))
    df["year_quarter"] = df["calendar_date"].apply(lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}")
    df["iso_week"] = df["calendar_date"].apply(lambda d: d.isocalendar()[1])
    df["iso_year"] = df["calendar_date"].apply(lambda d: d.isocalendar()[0])
    return df


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL missing from environment variables.")
    return database_url


def ensure_table_exists(engine):
    inspector = inspect(engine)
    if not inspector.has_table(TABLE_NAME):
        create_sql = f"""
            CREATE TABLE {TABLE_NAME} (
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
        print(f"Created {TABLE_NAME} table.")
    else:
        print(f"Table {TABLE_NAME} already exists.")


def load_existing_dates(engine) -> set:
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT calendar_date FROM {TABLE_NAME}"))
        return {row[0] for row in result.fetchall()}


def insert_missing_dates(engine, all_dates: pd.DataFrame):
    existing_dates = load_existing_dates(engine)
    missing_df = all_dates[~all_dates["calendar_date"].isin(existing_dates)]

    if missing_df.empty:
        print("Date table is already up to date.")
        return

    with engine.begin() as conn:
        missing_df.to_sql(
            TABLE_NAME,
            conn,
            if_exists="append",
            index=False,
            dtype={
                "calendar_date": Date(),
                "year": Integer(),
                "quarter": Integer(),
                "month": Integer(),
                "month_name": String(20),
                "day": Integer(),
                "day_of_week": Integer(),
                "day_name": String(20),
                "weekday": Integer(),
                "is_weekend": Boolean(),
                "year_month": String(7),
                "year_quarter": String(8),
                "iso_week": Integer(),
                "iso_year": Integer(),
            },
        )

    print(f"Inserted {len(missing_df)} new rows into {TABLE_NAME}.")


def main():
    database_url = get_database_url()
    engine = create_engine(database_url)

    today = date.today()
    df_calendar = build_date_table(START_DATE, today)

    ensure_table_exists(engine)
    insert_missing_dates(engine, df_calendar)

    print(f"Date table ready from {START_DATE} to {today}.")


if __name__ == "__main__":
    main()
