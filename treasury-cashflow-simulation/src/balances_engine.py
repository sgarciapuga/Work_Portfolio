import pandas as pd
from sqlalchemy import text

from utils.db import get_engine

def load_latest_balances():
    query = text(
        """
        SELECT account_number, closing_balance
        FROM treasury_balances
        WHERE date = (SELECT MAX(date) FROM treasury_balances)
        """
    )
    with get_engine().connect() as connection:
        return pd.read_sql(query, connection)

def prepare_accounts_df(accounts_df: pd.DataFrame) -> pd.DataFrame:
    latest = load_latest_balances()
    accounts_df = accounts_df.merge(latest, on="account_number", how="left")
    accounts_df.rename(columns={"closing_balance": "starting_balance"}, inplace=True)

    if "starting_balance" not in accounts_df.columns:
        accounts_df["starting_balance"] = 100000.0
    else:
        accounts_df["starting_balance"] = accounts_df["starting_balance"].fillna(100000.0)

    return accounts_df
