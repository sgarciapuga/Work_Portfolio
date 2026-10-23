"""Treasury simulator: Streamlit app.

Run from the repository root:

    streamlit run treasury-simulator/app/streamlit_app.py

Phase 1 shows the static data (group, accounts, facilities, IV commitments) and
the page structure. Daily history from Neon arrives in Phase 2.
"""

import streamlit as st

from common import sidebar

st.set_page_config(page_title="Treasury simulator", page_icon="🏦", layout="wide")

PAGES = [
    ("pages/overview.py", "Overview", "overview"),
    ("pages/today.py", "Today", "today"),
    ("pages/activity.py", "Activity", "activity"),
    ("pages/balance_sheet.py", "Balance sheet & NAV", "balance-sheet"),
    ("pages/market_data.py", "Market data", "market-data"),
    ("pages/positions.py", "Positions", "positions"),
    ("pages/forecast.py", "Forecast", "forecast"),
    ("pages/facilities.py", "Facilities & IV", "facilities"),
    ("pages/bank_accounts.py", "Bank accounts", "bank-accounts"),
    ("pages/learn.py", "Learn", "learn"),
]

nav = st.navigation([
    st.Page(path, title=title, url_path=url, default=(title == "Overview")) for path, title, url in PAGES
])
sidebar()
nav.run()
