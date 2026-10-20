"""Neon PostgreSQL helpers for the tsim schema.

The upsert follows the repo playbook: stage rows in a TEMP table, then
INSERT ... ON CONFLICT DO UPDATE on the primary key. The tables are new and
have primary keys from the start, so no legacy-duplicate clean-up is needed.
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import Date, MetaData, Table, create_engine, text

from tsim.static_data import load_static, validate

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = Path(__file__).resolve().parents[2] / "sql" / "tsim_schema.sql"
SCHEMA = "tsim"

# Static CSV -> (table, primary key columns). Order matters: parents before children.
STATIC_TABLES = [
    ("entities", "dim_entity", ["entity_code"]),
    ("banks", "dim_bank", ["bank_code"]),
    ("accounts", "dim_account", ["account_id"]),
    ("flow_codes", "dim_flow_code", ["flow_code"]),
    ("fee_schedule", "fee_schedule", ["schedule_id"]),
    ("iv_commitments", "iv_commitment", ["investment_id"]),
    ("facilities", "dim_facility", ["facility_id"]),
    ("mmf_funds", "dim_mmf_fund", ["fund_id"]),
]


def get_engine():
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL missing from environment variables.")
    return create_engine(url)


def schema_statements(sql_path=SCHEMA_SQL):
    """Split the schema file into single statements (comments removed).

    Comments are cut before splitting on ';', so a ';' inside a comment is harmless.
    The schema file has no '--' inside string literals.
    """
    lines = [line.split("--", 1)[0].rstrip()
             for line in Path(sql_path).read_text(encoding="utf-8").splitlines()]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def create_schema(engine):
    with engine.begin() as conn:
        for statement in schema_statements():
            conn.execute(text(statement))


def typed_for_table(conn, df, table):
    """(df, dtype) ready for to_sql into a table shaped like tsim.<table>.

    The column types come from the database, not from pandas. psycopg 3 (the
    driver of the CI DATABASE_URL) casts every text value to VARCHAR, and
    Postgres will not put a VARCHAR into a DATE, NUMERIC or BOOLEAN column;
    psycopg2 sent text untyped, so it worked locally. Date columns are also
    turned into real dates, since the static CSVs hold them as text.
    """
    target = Table(table, MetaData(), schema=SCHEMA, autoload_with=conn)
    dtype = {c.name: c.type for c in target.columns if c.name in df.columns}
    date_cols = [name for name, col_type in dtype.items() if isinstance(col_type, Date)]
    if date_cols:
        df = df.copy()
        for col in date_cols:
            df[col] = pd.to_datetime(df[col]).dt.date
    return df, dtype


def upsert(conn, df, table, key_cols):
    """Stage df in a TEMP table and upsert it into tsim.<table> on key_cols."""
    if df.empty:
        return 0
    staging = f"{table}_staging"
    conn.execute(text(
        f'CREATE TEMP TABLE "{staging}" (LIKE {SCHEMA}."{table}" INCLUDING DEFAULTS) ON COMMIT DROP'
    ))
    df, dtype = typed_for_table(conn, df, table)
    df.to_sql(staging, conn, if_exists="append", index=False, dtype=dtype)
    cols = list(df.columns)
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in key_cols)
    conflict = ", ".join(f'"{c}"' for c in key_cols)
    conn.execute(text(
        f'INSERT INTO {SCHEMA}."{table}" ({cols_sql}) '
        f'SELECT {cols_sql} FROM "{staging}" '
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    ))
    return len(df)


def load_static_to_db(engine, data=None):
    """Validate the static CSVs and upsert them into the tsim schema. Returns rows per table."""
    data = data or load_static()
    problems = validate(data)
    if problems:
        raise ValueError("Static data has problems:\n- " + "\n- ".join(problems))
    counts = {}
    with engine.begin() as conn:
        for name, table, keys in STATIC_TABLES:
            df = data[name].copy()
            if name == "facilities":
                df["secured"] = df["secured"].astype(str).str.lower() == "true"
            counts[table] = upsert(conn, df, table, keys)
    return counts


# ---------------------------------------------------------------
# Phase 2: engine outputs
# ---------------------------------------------------------------
# Engine table -> (tsim table, date column). The engine rebuilds history every run,
# so each table is refreshed by deleting the window and inserting it again:
# re-running gives the same rows, never more.
ENGINE_TABLES = {
    "cash_txn": ("cash_txn", "value_date"),
    "cash_balance": ("cash_balance", "balance_date"),
    "ic_current_account": ("ic_current_account", "balance_date"),
    "valuation": ("valuation", "valuation_date"),
    "nav_daily": ("nav_daily", "nav_date"),
    "alerts": ("alert", "alert_date"),
    "pnl_daily": ("pnl_daily", "pnl_date"),
}


def replace_window(conn, df, table, date_col, from_date=None):
    """Delete tsim.<table> rows on or after from_date (all rows if None), then insert df's rows in that window."""
    if from_date is None:
        conn.execute(text(f'DELETE FROM {SCHEMA}."{table}"'))
    else:
        conn.execute(text(f'DELETE FROM {SCHEMA}."{table}" WHERE "{date_col}" >= :d'), {"d": from_date})
        df = df[df[date_col] >= from_date]
    if not df.empty:
        df, dtype = typed_for_table(conn, df, table)
        df.to_sql(table, conn, schema=SCHEMA, if_exists="append", index=False, method="multi", chunksize=2000,
                  dtype=dtype)
    return len(df)


def save_engine_results(engine, results, rates=None, from_date=None):
    """Store the engine outputs (and the overnight rates) in Neon. Returns rows written per table."""
    counts = {}
    with engine.begin() as conn:
        for name, (table, date_col) in ENGINE_TABLES.items():
            counts[table] = replace_window(conn, results[name], table, date_col, from_date)
        counts["position"] = upsert(conn, results["position"], "position", ["position_id"])
        if rates is not None:
            counts["ir_rate"] = upsert(conn, rates, "ir_rate", ["rate_date", "currency", "tenor"])
    return counts
