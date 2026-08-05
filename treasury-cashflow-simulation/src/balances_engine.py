import pandas as pd
from utils.db import get_connection

def load_latest_balances():
    conn = get_connection()
    query = """
        SELECT account_number, closing_balance
        FROM balances
        WHERE date = (SELECT MAX(date) FROM balances)
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def prepare_accounts_df(accounts_df: pd.DataFrame) -> pd.DataFrame:
    latest = load_latest_balances()
    accounts_df = accounts_df.merge(latest, on="account_number", how="left")
    accounts_df.rename(columns={"closing_balance": "starting_balance"}, inplace=True)

    if "starting_balance" not in accounts_df.columns:
        accounts_df["starting_balance"] = 100000.0
    else:
        accounts_df["starting_balance"] = accounts_df["starting_balance"].fillna(100000.0)

    return accounts_df
