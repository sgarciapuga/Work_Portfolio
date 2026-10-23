import re

import pytest

from tsim.db import STATIC_TABLES, schema_statements

EXPECTED_TABLES = {
    "dim_entity", "dim_bank", "dim_account", "dim_flow_code", "fee_schedule", "iv_commitment",
    "dim_facility", "dim_mmf_fund", "ir_rate", "cash_txn", "cash_balance", "position",
    "fx_deal", "valuation", "forecast_line", "nav_daily", "scenario", "ic_current_account", "alert", "pnl_daily",
    "activity", "activity_plan",
}


def created_tables():
    return {m.group(1) for s in schema_statements()
            for m in [re.search(r"CREATE TABLE IF NOT EXISTS tsim\.(\w+)", s)] if m}


def test_all_design_tables_are_created():
    assert created_tables() == EXPECTED_TABLES


def test_static_tables_exist_in_schema():
    assert {table for _, table, _ in STATIC_TABLES} <= created_tables()


def test_every_statement_is_rerunnable():
    for s in schema_statements():
        assert ("IF NOT EXISTS" in s) or ("OR REPLACE" in s), s[:60]


def test_schema_parses_as_postgresql():
    pglast = pytest.importorskip("pglast")
    for s in schema_statements():
        pglast.parse_sql(s)
