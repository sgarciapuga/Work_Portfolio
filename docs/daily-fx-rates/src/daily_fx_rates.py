import argparse
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
import requests
from sqlalchemy import create_engine, inspect, text, Date

# Load environment variables from local .env file
load_dotenv()

TARGET_CURRENCIES = ["USD", "EUR", "GBP"]
HISTORY_START_DATE = datetime(2026, 1, 1).date()
QUALITY_RAW = "raw"
QUALITY_FILLED = "filled"
RECENT_FILLED_LOOKBACK_DAYS = 7

# Daily runs only work on the last DAILY_WINDOW_DAYS days.
# Once a week (and on the first run) the whole history is checked.
FULL_CHECK_WEEKDAY = 0  # Monday (0 = Monday ... 6 = Sunday)
DAILY_WINDOW_DAYS = 14


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


def _load_fx_from_db(engine, from_date=None):
    """Read fx_rates from Neon. Any database error stops the run."""
    query = "SELECT * FROM fx_rates"
    params = {}
    if from_date is not None:
        query += " WHERE date >= :from_date"
        params["from_date"] = from_date
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def update_fx_history(force_full=False):
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

    end_date = datetime.today().date()

    # ---------------------------------------------------------
    # Decide the run mode: weekly full check or daily window
    # ---------------------------------------------------------
    # A missing table is expected on the very first run only. Any other
    # database problem (connection, permissions) raises here and stops the run.
    table_exists = inspect(engine).has_table("fx_rates")
    csv_exists = os.path.exists(csv_path)

    full_check = (
        force_full
        or not table_exists
        or not csv_exists
        or end_date.weekday() == FULL_CHECK_WEEKDAY
    )
    window_start = end_date - timedelta(days=DAILY_WINDOW_DAYS)

    # ---------------------------------------------------------
    # Load existing FX from Neon DB
    # ---------------------------------------------------------
    df_db = _empty_fx_frame()
    if table_exists and not full_check:
        df_db = _normalize_fx_frame(_load_fx_from_db(engine, from_date=window_start))
        # The daily window needs stored rates at its start to carry forward.
        # If they are not there (for example the job did not run for a while),
        # fall back to the full check.
        if df_db.empty or min(df_db["date"]) > window_start:
            print("Stored data does not cover the daily window. Switching to full check.")
            full_check = True

    if table_exists and full_check:
        df_db = _normalize_fx_frame(_load_fx_from_db(engine))

    print("Run mode:", "FULL CHECK (whole history)" if full_check else f"DAILY (last {DAILY_WINDOW_DAYS} days)")

    # ---------------------------------------------------------
    # Load existing FX from CSV
    # ---------------------------------------------------------
    if csv_exists:
        df_csv = _normalize_fx_frame(pd.read_csv(csv_path))
    else:
        df_csv = _empty_fx_frame()

    if full_check:
        # Combine DB + CSV after key normalization.
        df_all = _normalize_fx_frame(pd.concat([df_db, df_csv], ignore_index=True))
    else:
        # Daily runs trust the database for the recent window.
        df_all = df_db

    # ---------------------------------------------------------
    # Determine latest stored date
    # ---------------------------------------------------------
    if df_all.empty:
        latest_date = HISTORY_START_DATE - timedelta(days=1)
        history_start = HISTORY_START_DATE
    elif full_check:
        latest_date = max(df_all["date"])
        history_start = min(min(df_all["date"]), HISTORY_START_DATE)
    else:
        latest_date = max(df_all["date"])
        history_start = window_start

    print("Latest stored FX date:", latest_date.strftime("%Y-%m-%d"))

    # ---------------------------------------------------------
    # Determine missing date range
    # ---------------------------------------------------------
    start_date = latest_date + timedelta(days=1)

    # Detect holes on business days so we can backfill them too
    # (whole history on a full check, last days on a daily run).
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

        # A failed API call must fail the run, so the workflow turns red
        # and the Slack alert is sent. Nothing is written in that case.
        if response.status_code != 200:
            raise RuntimeError(
                f"Frankfurter API request failed with status code {response.status_code}: {url}"
            )

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

    # USD is deterministic; non-USD are gap-filled across the series.
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
    if full_check:
        df_csv_out = df_final
    else:
        # Keep the older history as it is and replace only the daily window.
        df_csv_out = pd.concat(
            [df_csv[df_csv["date"] < history_start], df_final], ignore_index=True
        ).sort_values(by=["currency", "date"])
    df_csv_out.to_csv(csv_path, index=False)

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

        # Table maintenance only runs with the full check.
        if full_check:
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

        # Full check: every row. Daily run: only the rows of the daily window.
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
        f"FX history updated successfully. Sent {len(df_final)} rows to Neon DB. "
        f"Local CSV now has {len(df_csv_out)} rows."
    )
    print(df_final.tail())


# ---------------------------------------------------------
# Run script
# ---------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update the daily FX rates history.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Check and rebuild the whole history (this also happens automatically once a week).",
    )
    args = parser.parse_args()
    force_full = args.full or os.getenv("FX_FULL_CHECK", "").strip().lower() in ("1", "true", "yes")
    update_fx_history(force_full=force_full)
