import argparse
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
import requests
from sqlalchemy import create_engine, inspect, text, Date

# Load environment variables from local .env file
load_dotenv()

TARGET_CURRENCIES = ["USD", "EUR", "GBP", "CHF"]
# Currencies fetched from the API (USD is the base and always 1.0).
QUOTED_CURRENCIES = [c for c in TARGET_CURRENCIES if c != "USD"]
# 2025 history is needed by the treasury simulator (its backfill starts on 1 Jan 2025).
HISTORY_START_DATE = datetime(2025, 1, 1).date()
QUALITY_RAW = "raw"
QUALITY_FILLED = "filled"
RECENT_FILLED_LOOKBACK_DAYS = 7
# A full check stops if the API has rates for fewer business days than this
# share (ECB holidays are about 2-3%), rather than turn real history into filled rows.
MIN_MARKET_DAY_SHARE = 0.95
# Seconds to wait before the 2nd and 3rd attempts when the API fails for a moment.
API_RETRY_WAITS = (10, 30)

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


def _rows_from_api(rates_by_date):
    """Turn the Frankfurter 'rates' block into fx_rates rows (USD row = 1.0 each day)."""
    rows = []
    for date_str, rate_dict in rates_by_date.items():
        rows.append(
            {"date": date_str, "currency": "USD", "fx_to_usd": 1.00, "fx_quality_flag": QUALITY_RAW}
        )
        for currency in QUOTED_CURRENCIES:
            rows.append(
                {
                    "date": date_str,
                    "currency": currency,
                    "fx_to_usd": rate_dict.get(currency),
                    "fx_quality_flag": QUALITY_RAW,
                }
            )
    return rows


def build_daily_grid(df_inputs, start_date, end_date):
    """One row per calendar day and currency from start_date to end_date.

    df_inputs holds the rates to build from: market rates from the API and, on
    a daily run, the stored rows of the window. Days without a rate are carried
    forward from the last earlier rate of the same currency (or back from the
    first later one at the very start) and flagged filled. Inputs dated before
    start_date are only used to carry forward into it.
    """
    inputs = _normalize_fx_frame(df_inputs)
    first_date = min([start_date, *inputs["date"]])
    calendar_dates = pd.date_range(start=first_date, end=end_date, freq="D").date
    canonical_index = pd.MultiIndex.from_product(
        [calendar_dates, TARGET_CURRENCIES], names=["date", "currency"]
    )

    grid = (
        inputs.set_index(["date", "currency"])
        .reindex(canonical_index)
        .reset_index()
        .sort_values(by=["currency", "date"])
    )

    # USD is deterministic; non-USD are gap-filled within each currency.
    missing_before_fill = grid["fx_to_usd"].isna()
    grid.loc[grid["currency"] == "USD", "fx_to_usd"] = 1.0
    grid["fx_to_usd"] = grid.groupby("currency")["fx_to_usd"].transform(lambda s: s.ffill().bfill())
    grid["fx_quality_flag"] = grid["fx_quality_flag"].fillna(QUALITY_RAW)
    grid.loc[missing_before_fill & grid["fx_to_usd"].notna(), "fx_quality_flag"] = QUALITY_FILLED
    grid.loc[grid["currency"] == "USD", "fx_quality_flag"] = QUALITY_RAW

    return grid[grid["date"] >= start_date].reset_index(drop=True)


def daily_window_inputs(df_stored, df_fetched, window_start):
    """Rates a daily run builds its window from.

    Filled days are worked out again from the market rates, so they pick up any
    late correction. The first day of the window is kept whatever its flag, so
    the window carries on from the days before it. Fetched rows win over stored ones.
    """
    keep = (df_stored["fx_quality_flag"] == QUALITY_RAW) | (df_stored["date"] == window_start)
    return pd.concat([df_stored[keep], df_fetched], ignore_index=True)


def check_api_coverage(df_fetched, start_date, end_date):
    """Stop a full check when the API returned too little history to rebuild from."""
    business_days = len(pd.bdate_range(start=start_date, end=end_date))
    market_days = df_fetched.loc[df_fetched["date"] >= start_date, "date"].nunique()
    if market_days < MIN_MARKET_DAY_SHARE * business_days:
        raise RuntimeError(
            f"Frankfurter API returned rates for {market_days} of {business_days} business days "
            f"since {start_date}; refusing to rebuild the history from it."
        )


def fetch_api(url):
    """GET the Frankfurter API, retrying temporary failures (5xx, timeouts, dropped connections).

    Any other failure stops the run at once, so the workflow turns red and the
    Slack alert is sent. Nothing is written in that case.
    """
    for wait in (*API_RETRY_WAITS, None):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response
            error = RuntimeError(
                f"Frankfurter API request failed with status code {response.status_code}: {url}"
            )
            if response.status_code < 500:
                raise error
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = exc
        if wait is None:
            raise error
        print(f"{type(error).__name__} from the Frankfurter API; retrying in {wait}s")
        time.sleep(wait)


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
    expected_bdays = pd.bdate_range(start=history_start, end=end_date).date

    if full_check:
        # The full check rebuilds the whole history from the API, so a row is
        # raw only when the API has a rate for it. Stored rows are not reused:
        # older ones may carry a wrong flag or a filled value that is out of date.
        fetch_start = history_start
    else:
        start_date = latest_date + timedelta(days=1)

        # Detect holes on business days in the window so we can backfill them too.
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
            f"https://api.frankfurter.dev/v1/{start_str}..{end_str}?from=USD&to={','.join(QUOTED_CURRENCIES)}"
        )
        response = fetch_api(url)

        rates_by_date = response.json().get("rates", {})

        rows = _rows_from_api(rates_by_date)

        df_fetched = _normalize_fx_frame(pd.DataFrame(rows))

    # ---------------------------------------------------------
    # Build canonical daily grid and forward-fill per currency
    # ---------------------------------------------------------
    if full_check:
        check_api_coverage(df_fetched, history_start, end_date)
        df_inputs = df_fetched
    else:
        df_inputs = daily_window_inputs(df_all, df_fetched, history_start)

    df_final = build_daily_grid(df_inputs, history_start, end_date)

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
