import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_engine():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL missing from environment variables.")
    return create_engine(database_url)


def initialize_treasury_schema(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS treasury_balances (
                    date DATE NOT NULL,
                    account_number TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    starting_balance DOUBLE PRECISION NOT NULL,
                    total_movements DOUBLE PRECISION NOT NULL,
                    closing_balance DOUBLE PRECISION NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS treasury_balances_date_account_uidx
                ON treasury_balances (date, account_number)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS treasury_movements (
                    date DATE NOT NULL,
                    transaction_id TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS treasury_movements_date_transaction_account_uidx
                ON treasury_movements (date, transaction_id, account_number)
                """
            )
        )
