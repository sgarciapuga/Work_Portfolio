import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
import requests
from sqlalchemy import create_engine, text, Date

# Load environment variables from local .env file
load_dotenv()


def update_fx_history():
    # ---------------------------------------------------------
    # Credentials & Paths
    # ---------------------------------------------------------
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL missing from environment variables.")

    # Create SQLAlchemy engine for Neon PostgreSQL
    engine = create_engine(db_url)

    # Get absolute path to the directory where this script lives (src/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "..", "data", "fx_rates.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    # ---------------------------------------------------------
    # Load existing FX from Neon DB
    # ---------------------------------------------------------
    try:
        with engine.connect() as conn:
            df_db = pd.read_sql(text("SELECT * FROM fx_rates"), conn)
    except Exception:
        df_db = pd.DataFrame(columns=["date", "currency", "fx_to_usd"])

    # ---------------------------------------------------------
    # Load existing FX from CSV
    # ---------------------------------------------------------
    if os.path.exists(csv_path):
        df_csv = pd.read_csv(csv_path)
    else:
        df_csv = pd.DataFrame(columns=["date", "currency", "fx_to_usd"])

    # Combine DB + CSV & deduplicate
    df_all = pd.concat([df_db, df_csv]).drop_duplicates(
        subset=["date", "currency"]
    )

    # ---------------------------------------------------------
    # Determine latest stored date
    # ---------------------------------------------------------
    if df_all.empty:
        # Start from Jan 1, 2026
        latest_date = datetime(2026, 1, 1) - timedelta(days=1)
    else:
        latest_date = pd.to_datetime(df_all["date"]).max()

    print("Latest stored FX date:", latest_date.strftime("%Y-%m-%d"))

    # ---------------------------------------------------------
    # Determine missing date range
    # ---------------------------------------------------------
    start_date = latest_date + timedelta(days=1)
    end_date = datetime.today()

    if start_date.date() > end_date.date():
        print("FX data is already up to date. Ensuring local CSV backup is written...")
        # Write existing combined history to CSV so the file always exists
        df_all.to_csv(csv_path, index=False)
        return

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(f"Fetching FX from {start_str} to {end_str}...")

    # ---------------------------------------------------------
    # Fetch missing FX from Frankfurter API
    # ---------------------------------------------------------
    url = (
        f"https://api.frankfurter.app/{start_str}..{end_str}?from=USD&to=EUR,GBP"
    )
    response = requests.get(url)

    if response.status_code != 200:
        print(f"API request failed with status code {response.status_code}")
        return

    rates_by_date = response.json().get("rates", {})

    rows = []
    for date_str, rate_dict in rates_by_date.items():
        rows.append({"date": date_str, "currency": "USD", "fx_to_usd": 1.00})
        rows.append(
            {"date": date_str, "currency": "EUR", "fx_to_usd": rate_dict["EUR"]}
        )
        rows.append(
            {"date": date_str, "currency": "GBP", "fx_to_usd": rate_dict["GBP"]}
        )

    df_fetched = pd.DataFrame(rows)

    # ---------------------------------------------------------
    # Reindex over full date range & forward-fill missing days
    # ---------------------------------------------------------
    if not df_fetched.empty:
        all_dates = pd.date_range(
            start=start_date, end=end_date
        ).strftime("%Y-%m-%d")

        df_pivoted = df_fetched.pivot(
            index="date", columns="currency", values="fx_to_usd"
        ).reindex(all_dates)

        df_ff_long = (
            df_pivoted.reset_index()
            .rename(columns={"index": "date"})
            .melt(id_vars="date", var_name="currency", value_name="fx_to_usd")
        )
    else:
        df_ff_long = pd.DataFrame(columns=["date", "currency", "fx_to_usd"])

    # Combine with existing history
    df_final = (
        pd.concat([df_all, df_ff_long])
        .drop_duplicates(subset=["date", "currency"])
        .sort_values(by=["currency", "date"])
    )

    # Forward-fill any remaining NaNs across the grouped currency series
    df_final["fx_to_usd"] = (
        df_final.groupby("currency")["fx_to_usd"].ffill().bfill()
    )

    # Ensure date column is formatted as a datetime object
    df_final["date"] = pd.to_datetime(df_final["date"]).dt.date

    # ---------------------------------------------------------
    # Save to CSV
    # ---------------------------------------------------------
    df_final.to_csv(csv_path, index=False)

    # ---------------------------------------------------------
    # Save to Neon PostgreSQL Database
    # ---------------------------------------------------------
    with engine.begin() as conn:
        df_final.to_sql("fx_rates", conn, if_exists="replace", index=False, dtype={"date": Date()})

    print(
        f"FX history updated successfully. Saved {len(df_final)} rows to Neon DB and local CSV."
    )
    print(df_final.head())


# ---------------------------------------------------------
# Run script
# ---------------------------------------------------------
if __name__ == "__main__":
    update_fx_history()
