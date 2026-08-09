import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
import requests
from sqlalchemy import create_engine, text, Date

# Load environment variables from local .env file
load_dotenv()

TARGET_CURRENCIES = ["USD", "EUR", "GBP"]
HISTORY_START_DATE = datetime(2026, 1, 1).date()
QUALITY_RAW = "raw"
QUALITY_FILLED = "filled"
RECENT_FILLED_LOOKBACK_DAYS = 7


def _empty_fx_frame():
    return pd.DataFrame(columns=["date", "currency", "fx_to_usd", "fx_quality_flag"])


def _normalize_fx_frame(df):
    """Normalize schema and key fields so deduplication is reliable."""
    if df is None or df.empty:
        return _empty_fx_frame()

    working = df.copy()
    working.columns = [str(col).strip().lower() for col in working.columns]

    required = ["date", "currency", "fx_to_usd", "fx_quality_flag"]
    for col in required:
        if col not in working.columns:
            working[col] = pd.NA

    working = working[required]
    working["date"] = pd.to_datetime(working["date"], errors="coerce").dt.date
    working["currency"] = working["currency"].astype(str).str.upper().str.strip()
    working["fx_to_usd"] = pd.to_numeric(working["fx_to_usd"], errors="coerce")
    working["fx_quality_flag"] = (
        working["fx_quality_flag"]
        .astype(str)
        .str.lower()
        .where(lambda s: s.isin([QUALITY_RAW, QUALITY_FILLED]), QUALITY_RAW)
    )

    working = working.dropna(subset=["date", "currency"])
    working = working[working["currency"].isin(TARGET_CURRENCIES)]
    working = working.drop_duplicates(subset=["date", "currency"], keep="last")

    return working


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
        df_db = _empty_fx_frame()

    # ---------------------------------------------------------
    # Load existing FX from CSV
    # ---------------------------------------------------------
    if os.path.exists(csv_path):
        df_csv = pd.read_csv(csv_path)
    else:
        df_csv = _empty_fx_frame()

    # Combine DB + CSV after key normalization.
    df_all = _normalize_fx_frame(pd.concat([_normalize_fx_frame(df_db), _normalize_fx_frame(df_csv)], ignore_index=True))

    # ---------------------------------------------------------
    # Determine latest stored date
    # ---------------------------------------------------------
    if df_all.empty:
        latest_date = HISTORY_START_DATE - timedelta(days=1)
        history_start = HISTORY_START_DATE
    else:
        latest_date = max(df_all["date"])
        history_start = min(min(df_all["date"]), HISTORY_START_DATE)

    print("Latest stored FX date:", latest_date.strftime("%Y-%m-%d"))

    # ---------------------------------------------------------
    # Determine missing date range
    # ---------------------------------------------------------
    start_date = latest_date + timedelta(days=1)
    end_date = datetime.today().date()

    # Detect historical holes on business days so we can backfill them too.
    expected_bdays = pd.bdate_range(start=history_start, end=end_date).date
    expected_index = pd.MultiIndex.from_product(
        [expected_bdays, TARGET_CURRENCIES], names=["date", "currency"]
    )

    missing_index = expected_index.difference(
        pd.MultiIndex.from_frame(df_all[["date", "currency"]])
    )

    missing_business_days = sorted({idx[0] for idx in missing_index})

    if missing_business_days:
        fetch_start = min(start_date, missing_business_days[0])
        print(
            f"Detected {len(missing_index)} missing business-day currency rows. Backfilling from {fetch_start}..."
        )
    else:
        fetch_start = start_date

    # Re-check recently filled rows because the source may have published late data.
    lookback_start = end_date - timedelta(days=RECENT_FILLED_LOOKBACK_DAYS)
    recent_filled_dates = sorted(
        set(
            df_all.loc[
                (df_all["fx_quality_flag"] == QUALITY_FILLED)
                & (df_all["date"] >= lookback_start),
                "date",
            ]
        )
    )
    if recent_filled_dates:
        fetch_start = min(fetch_start, recent_filled_dates[0])
        print(
            f"Rechecking {len(recent_filled_dates)} recently filled day(s) from {recent_filled_dates[0]}..."
        )

    if fetch_start > end_date:
        print("FX data is already up to date. Rebuilding clean history and writing outputs...")
        df_fetched = _empty_fx_frame()
    else:
        start_str = fetch_start.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        print(f"Fetching FX from {start_str} to {end_str}...")

    # ---------------------------------------------------------
    # Fetch missing FX from Frankfurter API
    # ---------------------------------------------------------
        url = (
            f"https://api.frankfurter.app/{start_str}..{end_str}?from=USD&to=EUR,GBP"
        )
        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            print(f"API request failed with status code {response.status_code}")
            return

        rates_by_date = response.json().get("rates", {})

        rows = []
        for date_str, rate_dict in rates_by_date.items():
            rows.append(
                {
                    "date": date_str,
                    "currency": "USD",
                    "fx_to_usd": 1.00,
                    "fx_quality_flag": QUALITY_RAW,
                }
            )
            rows.append(
                {
                    "date": date_str,
                    "currency": "EUR",
                    "fx_to_usd": rate_dict.get("EUR"),
                    "fx_quality_flag": QUALITY_RAW,
                }
            )
            rows.append(
                {
                    "date": date_str,
                    "currency": "GBP",
                    "fx_to_usd": rate_dict.get("GBP"),
                    "fx_quality_flag": QUALITY_RAW,
                }
            )

        df_fetched = _normalize_fx_frame(pd.DataFrame(rows))

    # ---------------------------------------------------------
    # Build canonical daily grid and forward-fill per currency
    # ---------------------------------------------------------
    df_raw = _normalize_fx_frame(pd.concat([df_all, df_fetched], ignore_index=True))

    calendar_dates = pd.date_range(start=history_start, end=end_date, freq="D").date
    canonical_index = pd.MultiIndex.from_product(
        [calendar_dates, TARGET_CURRENCIES], names=["date", "currency"]
    )

    df_final = (
        df_raw.set_index(["date", "currency"])
        .reindex(canonical_index)
        .reset_index()
        .sort_values(by=["currency", "date"])
    )

    # USD is deterministic; non-USD are gap-filled across the historical series.
    missing_before_fill = df_final["fx_to_usd"].isna()
    df_final.loc[df_final["currency"] == "USD", "fx_to_usd"] = 1.0
    df_final["fx_to_usd"] = df_final.groupby("currency")["fx_to_usd"].ffill().bfill()
    df_final["fx_quality_flag"] = df_final["fx_quality_flag"].where(
        df_final["fx_quality_flag"].isin([QUALITY_RAW, QUALITY_FILLED]), QUALITY_RAW
    )
    df_final.loc[missing_before_fill & df_final["fx_to_usd"].notna(), "fx_quality_flag"] = QUALITY_FILLED
    df_final.loc[df_final["currency"] == "USD", "fx_quality_flag"] = QUALITY_RAW

    missing_after_fill = (
        df_final[df_final["date"].isin(expected_bdays)]
        .groupby("currency")["fx_to_usd"]
        .apply(lambda s: s.isna().sum())
    )
    still_missing = missing_after_fill[missing_after_fill > 0]
    if not still_missing.empty:
        raise RuntimeError(
            "Missing FX values remain on business days after fill: "
            + ", ".join(f"{k}={v}" for k, v in still_missing.items())
        )

    # ---------------------------------------------------------
    # Save to CSV
    # ---------------------------------------------------------
    df_final.to_csv(csv_path, index=False)

    # ---------------------------------------------------------
    # Save to Neon PostgreSQL Database (idempotent upsert)
    # ---------------------------------------------------------
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fx_rates (
                    date DATE NOT NULL,
                    currency TEXT NOT NULL,
                    fx_to_usd DOUBLE PRECISION NOT NULL,
                    fx_quality_flag TEXT NOT NULL DEFAULT 'raw'
                )
                """
            )
        )

        conn.execute(
            text(
                """
                ALTER TABLE fx_rates
                ADD COLUMN IF NOT EXISTS fx_quality_flag TEXT NOT NULL DEFAULT 'raw'
                """
            )
        )

        # Clean up any legacy duplicates so a unique key can be enforced.
        conn.execute(
            text(
                """
                DELETE FROM fx_rates a
                USING fx_rates b
                WHERE a.ctid < b.ctid
                  AND a.date = b.date
                  AND a.currency = b.currency
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS fx_rates_date_currency_uidx
                ON fx_rates (date, currency)
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TEMP TABLE fx_rates_staging (
                    date DATE NOT NULL,
                    currency TEXT NOT NULL,
                    fx_to_usd DOUBLE PRECISION NOT NULL,
                    fx_quality_flag TEXT NOT NULL
                ) ON COMMIT DROP
                """
            )
        )

        df_final.to_sql(
            "fx_rates_staging",
            conn,
            if_exists="append",
            index=False,
            dtype={"date": Date()},
        )

        conn.execute(
            text(
                """
                INSERT INTO fx_rates (date, currency, fx_to_usd, fx_quality_flag)
                SELECT date, currency, fx_to_usd, fx_quality_flag
                FROM fx_rates_staging
                ON CONFLICT (date, currency)
                DO UPDATE SET
                    fx_to_usd = EXCLUDED.fx_to_usd,
                    fx_quality_flag = EXCLUDED.fx_quality_flag
                """
            )
        )

    print(
        f"FX history updated successfully. Saved {len(df_final)} rows to Neon DB and local CSV."
    )
    print(df_final.head())


# ---------------------------------------------------------
# Run script
# ---------------------------------------------------------
if __name__ == "__main__":
    update_fx_history()
