"""Neon PostgreSQL helpers for the tsim schema.

The upsert follows the repo playbook: stage rows in a TEMP table, then
INSERT ... ON CONFLICT DO UPDATE on the primary key. The tables are new and
have primary keys from the start, so no legacy-duplicate clean-up is needed.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, text

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


def upsert(conn, df, table, key_cols):
    """Stage df in a TEMP table and upsert it into tsim.<table> on key_cols."""
    if df.empty:
        return 0
    staging = f"{table}_staging"
    conn.execute(text(
        f'CREATE TEMP TABLE "{staging}" (LIKE {SCHEMA}."{table}" INCLUDING DEFAULTS) ON COMMIT DROP'
    ))
    df.to_sql(staging, conn, if_exists="append", index=False)
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
