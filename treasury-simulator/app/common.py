"""Shared helpers for the treasury simulator app: static data, settings sidebar, tier badges."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tsim import config  # noqa: E402
from tsim.static_data import load_static, validate  # noqa: E402

TIER_COLORS = {1: "#1E8E3E", 2: "#3B78E7", 3: "#F08C2E", 4: "#9AA0A6"}
# One colour per currency on every chart (first three validated categorical slots).
CCY_COLORS = {"EUR": "#2a78d6", "GBP": "#eb6834", "CHF": "#1baf7a", "USD": "#6250d6"}
RESULT_TABLES = {  # app name -> (tsim table, date column)
    "nav_daily": ("nav_daily", "nav_date"),
    "cash_balance": ("cash_balance", "balance_date"),
    "ic_current_account": ("ic_current_account", "balance_date"),
    "valuation": ("valuation", "valuation_date"),
    "alerts": ("alert", "alert_date"),
    "pnl_daily": ("pnl_daily", "pnl_date"),
}


@st.cache_data
def static_data():
    data = load_static()
    problems = validate(data)
    return data, problems


@st.cache_data
def glossary():
    return pd.read_csv(PROJECT_DIR / "static" / "glossary.csv", keep_default_na=False)


def data_dir():
    """CSV backups folder (TSIM_DATA_DIR overrides it, e.g. in tests)."""
    import os

    return Path(os.getenv("TSIM_DATA_DIR", PROJECT_DIR / "data"))


def _database_url():
    import os

    if os.getenv("TSIM_NO_DB"):  # tests: never touch the real database
        return None
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:  # no secrets.toml
        url = None
    if not url:
        try:
            from dotenv import load_dotenv

            load_dotenv(PROJECT_DIR.parent / ".env")
        except ImportError:
            pass
        url = os.getenv("DATABASE_URL")
    return url


@st.cache_data(ttl=3600, show_spinner="Loading the simulated history...")
def results():
    """Engine outputs from Neon (tsim schema), or the CSV backups in treasury-simulator/data/.

    Returns (dict of DataFrames, source label). Empty dict when nothing has been generated yet.
    """
    url = _database_url()
    if url:
        try:
            from sqlalchemy import create_engine

            engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
            with engine.connect() as conn:
                out = {name: pd.read_sql(f'SELECT * FROM tsim."{table}"', conn) for name, (table, _) in RESULT_TABLES.items()}
            if not out["nav_daily"].empty:
                return _dates(out), "Neon PostgreSQL (tsim schema)"
        except Exception:
            pass
    folder = data_dir()
    if not (folder / "nav_daily.csv").exists():
        return {}, "none"
    out = {name: pd.read_csv(folder / f"{name}.csv") if (folder / f"{name}.csv").exists()
           else pd.DataFrame(columns=[col]) for name, (_, col) in RESULT_TABLES.items()}
    return _dates(out), "CSV backup (treasury-simulator/data)"


def _dates(tables):
    """Date columns as dates; NUMERIC columns from Neon (Decimal) as floats."""
    from decimal import Decimal

    for name, (_, col) in RESULT_TABLES.items():
        df = tables[name]
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.date
        for c in df.columns:
            if df[c].dtype == object and df[c].map(lambda v: isinstance(v, Decimal)).any():
                df[c] = df[c].astype(float)
    return tables


def no_history_message():
    st.info("No simulated history yet. From the repository root run "
            "`python treasury-simulator/run_daily.py --fetch-rates` (CSV only) or wait for the daily workflow.")


def as_of():
    """The as-of date chosen in the sidebar (latest simulated day by default)."""
    return st.session_state.get("as_of_day")


def tier_badge(tier):
    """Small coloured label: how deeply this feature is built (see the design doc's tier map)."""
    color = TIER_COLORS[tier]
    label = f"Tier {tier} · {config.TIERS[tier]}"
    return (f'<span style="background:{color}22;color:{color};border:1px solid {color};'
            f'border-radius:10px;padding:1px 8px;font-size:0.8rem;font-weight:600">{label}</span>')


def page_header(title, tier, intro):
    st.title(title)
    st.markdown(tier_badge(tier), unsafe_allow_html=True)
    st.caption(intro)


def coming_soon(phase, items):
    st.info(f"This page is built in Phase {phase}. It will show:")
    for item in items:
        st.markdown(f"- {item}")


def money(value, ccy="USD"):
    if abs(value) >= 1e9:
        return f"{ccy} {value / 1e9:,.2f}bn"
    if abs(value) >= 1e6:
        return f"{ccy} {value / 1e6:,.0f}m"
    return f"{ccy} {value:,.0f}"


def sidebar():
    """Settings shared by every page. Stored in st.session_state."""
    with st.sidebar:
        st.header("Settings")
        data, _ = results()
        if data:
            days = sorted(data["nav_daily"]["nav_date"].unique())
            st.date_input("As-of date", value=days[-1], min_value=days[0], max_value=days[-1], key="as_of_day")
        else:
            st.date_input("As-of date", value=config.HISTORY_START, disabled=True, help="No history yet.")
        st.selectbox("Group profile", ["Investment group", "Corporate group (later)"], key="profile",
                     disabled=True)
        st.radio("Forecast case", ["Downside", "Base", "Upside"], index=1, key="case", horizontal=True)
        st.selectbox("Scenario", ["None (base history)"], key="scenario",
                     help="What-if scenarios arrive in Phase 6.")
