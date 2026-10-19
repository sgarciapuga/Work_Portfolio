import pandas as pd
import streamlit as st

from common import config, money, page_header, static_data

page_header("Aldmere Group: treasury overview", 1,
            "A made-up investment group. London treasury (TRS) is the in-house bank for every entity.")

data, problems = static_data()
if problems:
    st.error("Static data problems: " + "; ".join(problems))

iv = data["iv_commitments"]
fac = data["facilities"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Facilities (secured + RCF)", money(fac["limit_amount"].sum()))
c2.metric("IV buffer (minimum)", money(config.IV_BUFFER_USD))
c3.metric("FX tolerance per currency", money(config.FX_TOLERANCE_USD))
c4.metric("Operating cash per currency", money(config.OPERATING_MIN_USD))

st.subheader("Group entities")
st.dataframe(data["entities"], hide_index=True, width="stretch")

st.subheader("IV commitments by currency")
by_ccy = iv.assign(uncalled=iv["commitment"] * (1 - iv["called_pct_at_start"])) \
    .groupby("currency")[["commitment", "uncalled"]].sum().reset_index()
st.dataframe(by_ccy, hide_index=True, column_config={
    "commitment": st.column_config.NumberColumn("Commitment", format="localized"),
    "uncalled": st.column_config.NumberColumn(f"Uncalled at {config.HISTORY_START:%d %b %Y}", format="localized"),
})

st.info("KPI tiles, NAV and headroom trends arrive in Phase 2, once the daily history is in Neon.")
