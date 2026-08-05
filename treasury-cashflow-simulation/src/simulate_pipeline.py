import os
import pandas as pd
import random
from datetime import datetime, timedelta

from utils.logging import setup_logging
from utils.dates import today_str
from utils.db import get_connection
from config import get_balances_path, get_movements_path
from load_static import load_static_data
from generate_movements import generate_movements
from sweep_engine import sweep_cash
from balances_engine import prepare_accounts_df

logger = setup_logging("treasury-simulation")

def get_last_date(conn):
    row = conn.execute("SELECT MAX(date) FROM balances").fetchone()
    return row[0] if row and row[0] is not None else None

def ensure_output_dirs():
    os.makedirs(get_balances_path(), exist_ok=True)
    os.makedirs(get_movements_path(), exist_ok=True)

def simulate_pipeline():
    conn = get_connection()
    ensure_output_dirs()

    accounts_df, movement_types_df = load_static_data()

    last_date = get_last_date(conn)

    if last_date is None:
        start_date = "2026-01-02"
        accounts_df["starting_balance"] = [
            round(random.uniform(100000, 500000), 2)
            for _ in range(len(accounts_df))
        ]
        logger.info(f"Database empty â†’ full backfill from {start_date}")
    else:
        next_date = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)
        start_date = next_date.strftime("%Y-%m-%d")
        logger.info(f"Incremental update from {start_date}")
        accounts_df = prepare_accounts_df(accounts_df)

    end_date = today_str()

    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        movements = generate_movements(date_str, accounts_df)
        movement_sum = movements.groupby("account_number")["amount"].sum().reset_index()
        movement_sum.rename(columns={"amount": "total_movements"}, inplace=True)

        daily = accounts_df.merge(movement_sum, on="account_number", how="left")
        daily["total_movements"] = daily["total_movements"].fillna(0)
        daily["closing_balance"] = daily["starting_balance"] + daily["total_movements"]
        daily["date"] = date_str

        daily, sweep_movements = sweep_cash(daily)
        movements = pd.concat([movements, sweep_movements], ignore_index=True)

        # Export CSVs
        daily.to_csv(
            os.path.join(get_balances_path(), f"balances_{date_str.replace('-', '')}.csv"),
            index=False
        )
        movements.to_csv(
            os.path.join(get_movements_path(), f"movements_{date_str.replace('-', '')}.csv"),
            index=False
        )

        # Insert into DB
        daily_db = daily[[
            "date",
            "account_number",
            "currency",
            "starting_balance",
            "total_movements",
            "closing_balance"
        ]]
        daily_db.to_sql("balances", conn, if_exists="append", index=False)
        movements.to_sql("movements", conn, if_exists="append", index=False)

        # Prepare next day
        accounts_df = daily[["account_number", "currency", "closing_balance"]]
        accounts_df.rename(columns={"closing_balance": "starting_balance"}, inplace=True)

        logger.info(f"Inserted data for {date_str}")
        current += timedelta(days=1)

    conn.close()
    logger.info("Simulation complete.")
