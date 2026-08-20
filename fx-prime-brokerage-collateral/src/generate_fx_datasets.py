import argparse
import os
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from generate_limits import generate_limits
from generate_mtm_for_portfolio import generate_mtm_for_portfolio
from generate_mtm_report import generate_mtm_report
from generate_fx_portfolio import generate_fx_portfolio
from sqlalchemy import Date, create_engine, text


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _last_date_in_csv(csv_path, date_col):
    """Return the max date already present in an existing CSV, or None if absent/empty."""
    path = Path(csv_path)
    if not path.exists() or path.stat().st_size == 0:
        return None
    existing = pd.read_csv(path, usecols=[date_col])
    if existing.empty:
        return None
    return pd.to_datetime(existing[date_col]).max()


def _incremental_slice(df, date_col, last_date):
    """Return only the rows newer than ``last_date`` (or the full frame if there is none)."""
    if df is None or df.empty or last_date is None:
        return df
    dates = pd.to_datetime(df[date_col])
    return df.loc[dates > last_date].reset_index(drop=True)


def _write_csv(df, csv_path, last_date):
    """Write the full frame on first run, or append only the new rows thereafter."""
    if df is None:
        return
    path = Path(csv_path)
    if last_date is None or not path.exists():
        df.to_csv(path, index=False)
        return
    if df.empty:
        return
    df.to_csv(path, mode="a", index=False, header=False)


def _ensure_database_url():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL missing from environment variables.")
    return db_url


def _quote_ident(identifier):
    return f'"{identifier}"'


def _delete_legacy_duplicates(conn, table_name, unique_cols):
    partition = ", ".join(_quote_ident(col) for col in unique_cols)
    conn.execute(
        text(
            f"""
            DELETE FROM {_quote_ident(table_name)}
            WHERE ctid IN (
                SELECT ctid
                FROM (
                    SELECT ctid,
                           ROW_NUMBER() OVER (
                               PARTITION BY {partition}
                               ORDER BY ctid DESC
                           ) AS rn
                    FROM {_quote_ident(table_name)}
                ) dedup
                WHERE dedup.rn > 1
            )
            """
        )
    )


def _create_unique_index(conn, table_name, unique_cols):
    index_name = f"{table_name}_{'_'.join(unique_cols)}_uidx"
    cols = ", ".join(_quote_ident(col) for col in unique_cols)
    conn.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {_quote_ident(index_name)}
            ON {_quote_ident(table_name)} ({cols})
            """
        )
    )


def _upsert_dataframe(conn, df, table_name, unique_cols, date_cols=None):
    if df is None or df.empty:
        return

    working = df.copy()
    date_cols = date_cols or []
    for col in date_cols:
        if col in working.columns:
            working[col] = working[col].astype("string")

    staging_table = f"{table_name}_staging"
    conn.execute(
        text(
            f"""
            CREATE TEMP TABLE {_quote_ident(staging_table)}
            (LIKE {_quote_ident(table_name)} INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
    )

    dtype = {col: Date() for col in date_cols if col in working.columns}
    working.to_sql(
        staging_table,
        conn,
        if_exists="append",
        index=False,
        dtype=dtype,
    )

    columns = list(working.columns)
    cols_csv = ", ".join(_quote_ident(col) for col in columns)
    update_cols = [col for col in columns if col not in unique_cols]
    update_set = ",\n                    ".join(
        f"{_quote_ident(col)} = EXCLUDED.{_quote_ident(col)}" for col in update_cols
    )
    conflict_cols = ", ".join(_quote_ident(col) for col in unique_cols)

    conn.execute(
        text(
            f"""
            INSERT INTO {_quote_ident(table_name)} ({cols_csv})
            SELECT {cols_csv}
            FROM {_quote_ident(staging_table)}
            ON CONFLICT ({conflict_cols})
            DO UPDATE SET
                    {update_set}
            """
        )
    )


def _save_to_database(df_limits, df_mtm_portfolio, df_mtm_report, df_fx_portfolio):
    db_url = _ensure_database_url()
    engine = create_engine(db_url)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fx_prime_limits (
                    as_of_date DATE NOT NULL,
                    bank_id TEXT NOT NULL,
                    credit_limit_usd DOUBLE PRECISION NOT NULL,
                    counterparty_exposure_usd DOUBLE PRECISION NOT NULL,
                    limit_available_usd DOUBLE PRECISION NOT NULL
                )
                """
            )
        )
        _delete_legacy_duplicates(conn, "fx_prime_limits", ["as_of_date", "bank_id"])
        _create_unique_index(conn, "fx_prime_limits", ["as_of_date", "bank_id"])
        _upsert_dataframe(
            conn,
            df_limits,
            "fx_prime_limits",
            unique_cols=["as_of_date", "bank_id"],
            date_cols=["as_of_date"],
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fx_prime_mark_to_market_portfolio (
                    report_date DATE NOT NULL,
                    trade_id TEXT NOT NULL,
                    bank_id TEXT NOT NULL,
                    mtm DOUBLE PRECISION NOT NULL,
                    pnl DOUBLE PRECISION NOT NULL,
                    trade_size_usd DOUBLE PRECISION NOT NULL
                )
                """
            )
        )
        _delete_legacy_duplicates(
            conn,
            "fx_prime_mark_to_market_portfolio",
            ["report_date", "trade_id", "bank_id"],
        )
        _create_unique_index(
            conn,
            "fx_prime_mark_to_market_portfolio",
            ["report_date", "trade_id", "bank_id"],
        )
        _upsert_dataframe(
            conn,
            df_mtm_portfolio,
            "fx_prime_mark_to_market_portfolio",
            unique_cols=["report_date", "trade_id", "bank_id"],
            date_cols=["report_date"],
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fx_prime_mtm_report (
                    report_date DATE NOT NULL,
                    initial_margin DOUBLE PRECISION NOT NULL,
                    variation_margin DOUBLE PRECISION NOT NULL,
                    collateral_required DOUBLE PRECISION NOT NULL,
                    collateral_posted DOUBLE PRECISION NOT NULL,
                    excess_deficit DOUBLE PRECISION NOT NULL
                )
                """
            )
        )
        _delete_legacy_duplicates(conn, "fx_prime_mtm_report", ["report_date"])
        _create_unique_index(conn, "fx_prime_mtm_report", ["report_date"])
        _upsert_dataframe(
            conn,
            df_mtm_report,
            "fx_prime_mtm_report",
            unique_cols=["report_date"],
            date_cols=["report_date"],
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fx_prime_portfolio (
                    report_date DATE NOT NULL,
                    bank_id TEXT NOT NULL,
                    trade_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    value_date DATE NOT NULL,
                    currency_pair TEXT NOT NULL,
                    trade_size_usd DOUBLE PRECISION NOT NULL,
                    leg_id INTEGER NOT NULL
                )
                """
            )
        )
        _delete_legacy_duplicates(
            conn,
            "fx_prime_portfolio",
            ["report_date", "bank_id", "trade_id", "leg_id"],
        )
        _create_unique_index(
            conn,
            "fx_prime_portfolio",
            ["report_date", "bank_id", "trade_id", "leg_id"],
        )
        _upsert_dataframe(
            conn,
            df_fx_portfolio,
            "fx_prime_portfolio",
            unique_cols=["report_date", "bank_id", "trade_id", "leg_id"],
            date_cols=["report_date", "trade_date", "value_date"],
        )

    print("Saved datasets to PostgreSQL with idempotent upserts:")
    print("- fx_prime_limits")
    print("- fx_prime_mark_to_market_portfolio")
    print("- fx_prime_mtm_report")
    print("- fx_prime_portfolio")


# The generated FX datasets are intended to run up to yesterday COB by default.
def run_all(out_dir=None):
    """Generate all four datasets, write CSV files, and persist them to PostgreSQL."""
    base = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "data"
    limits_dir = base / "Limits"
    mtm_dir = base / "Mark-to-market"
    fx_portfolio_dir = base / "FX-portfolio"
    limits_dir.mkdir(parents=True, exist_ok=True)
    mtm_dir.mkdir(parents=True, exist_ok=True)
    fx_portfolio_dir.mkdir(parents=True, exist_ok=True)

    limits_file = limits_dir / "limits.csv"
    mtm_portfolio_file = mtm_dir / "mark_to_market_portfolio.csv"
    mtm_report_file = mtm_dir / "mtm_report.csv"
    fx_portfolio_file = fx_portfolio_dir / "portfolio.csv"

    # Determine, per dataset, whether this is a first run (write from scratch)
    # or a subsequent run (only the rows after the last generated date are new).
    last_fx_portfolio_date = _last_date_in_csv(fx_portfolio_file, "report_date")
    last_limits_date = _last_date_in_csv(limits_file, "as_of_date")
    last_mtm_portfolio_date = _last_date_in_csv(mtm_portfolio_file, "report_date")
    last_mtm_report_date = _last_date_in_csv(mtm_report_file, "report_date")

    df_fx_portfolio = generate_fx_portfolio()
    df_mtm_portfolio = generate_mtm_for_portfolio(df_fx_portfolio)
    df_limits = generate_limits(portfolio_df=df_fx_portfolio)
    # generate_mtm_report() writes its own full copy internally; redirect that
    # throwaway write outside of data/ so it doesn't clobber our incremental write below.
    with tempfile.TemporaryDirectory() as scratch_dir:
        df_mtm_report = generate_mtm_report(
            portfolio_df=df_fx_portfolio, mtm_df=df_mtm_portfolio, out_path=scratch_dir
        )

    new_fx_portfolio = _incremental_slice(df_fx_portfolio, "report_date", last_fx_portfolio_date)
    new_limits = _incremental_slice(df_limits, "as_of_date", last_limits_date)
    new_mtm_portfolio = _incremental_slice(df_mtm_portfolio, "report_date", last_mtm_portfolio_date)
    new_mtm_report = _incremental_slice(df_mtm_report, "report_date", last_mtm_report_date)

    _write_csv(new_limits, limits_file, last_limits_date)
    _write_csv(new_mtm_portfolio, mtm_portfolio_file, last_mtm_portfolio_date)
    _write_csv(new_mtm_report, mtm_report_file, last_mtm_report_date)
    _write_csv(new_fx_portfolio, fx_portfolio_file, last_fx_portfolio_date)

    _save_to_database(new_limits, new_mtm_portfolio, new_mtm_report, new_fx_portfolio)

    mode = "from scratch" if last_fx_portfolio_date is None else "incrementally"
    row_count = lambda df: 0 if df is None else len(df)
    print(f"Wrote limits {mode} -> {limits_file} (+{row_count(new_limits)} rows)")
    print(f"Wrote mark-to-market portfolio {mode} -> {mtm_portfolio_file} (+{row_count(new_mtm_portfolio)} rows)")
    print(f"Wrote mark-to-market report {mode} -> {mtm_report_file} (+{row_count(new_mtm_report)} rows)")
    print(f"Wrote FX portfolio {mode} -> {fx_portfolio_file} (+{row_count(new_fx_portfolio)} rows)")



def main():
    """Parse the command-line output directory and run the complete pipeline."""
    p = argparse.ArgumentParser(description="Generate synthetic FX prime brokerage collateral datasets")
    p.add_argument("--out", help="Output base directory (defaults to repo fx-prime-brokerage-collateral/data)")
    args = p.parse_args()
    run_all(args.out)


if __name__ == "__main__":
    main()
