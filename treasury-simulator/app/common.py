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


@st.cache_data
def static_data():
    data = load_static()
    problems = validate(data)
    return data, problems


@st.cache_data
def glossary():
    return pd.read_csv(PROJECT_DIR / "static" / "glossary.csv", keep_default_na=False)


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
        st.date_input("As-of date", value=config.HISTORY_START, key="as_of", disabled=True,
                      help="Daily history arrives in Phase 2.")
        st.selectbox("Group profile", ["Investment group", "Corporate group (later)"], key="profile",
                     disabled=True)
        st.radio("Forecast case", ["Downside", "Base", "Upside"], index=1, key="case", horizontal=True)
        st.selectbox("Scenario", ["None (base history)"], key="scenario",
                     help="What-if scenarios arrive in Phase 6.")
