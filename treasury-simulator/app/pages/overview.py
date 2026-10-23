import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import CCY_COLORS, as_of, config, money, no_history_message, page_header, results, static_data

page_header("Aldmere Group: treasury overview", 1,
            "A made-up investment group. London treasury (TRS) is the in-house bank for every entity.")

data, problems = static_data()
if problems:
    st.error("Static data problems: " + "; ".join(problems))

hist, source = results()
if not hist:
    no_history_message()
else:
    day = as_of()
    nav = hist["nav_daily"]
    today = nav[nav["nav_date"] == day].set_index("currency")
    val = hist["valuation"]
    val_day = val[(val["valuation_date"] == day) & (val["item_type"] == "position")]
    invested = val_day[val_day["value_ccy"] > 0]["value_usd"].sum()
    iv_deposit = -val_day[val_day["item_id"].str.startswith("ICD-IV")]["value_usd"].sum()
    open_fx = today.drop(index="USD")["open_fx_position_usd"]
    worst = open_fx.abs().idxmax()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TRS NAV (USD)", money(today["nav_usd"].sum()))
    c2.metric("MMFs and deposits (USD)", money(invested))
    c3.metric("IV buffer at TRS", money(iv_deposit),
              help=f"Minimum {money(config.IV_BUFFER_USD)}")
    breach = abs(open_fx[worst]) > config.FX_TOLERANCE_USD
    c4.metric(f"Largest open FX: {worst}", money(open_fx[worst]),
              delta="Outside ±50k tolerance" if breach else "Within ±50k tolerance",
              delta_color="inverse" if breach else "off")
    if breach:
        st.caption("The autopilot trades spot to bring a currency back inside the tolerance on its next business day.")

    st.subheader("TRS NAV in USD")
    total = nav.groupby("nav_date", as_index=False)["nav_usd"].sum()
    fig = go.Figure(go.Scatter(x=total["nav_date"], y=total["nav_usd"], mode="lines",
                               line=dict(width=2, color=CCY_COLORS["USD"]),
                               hovertemplate="%{x|%d %b %Y}<br>USD %{y:,.0f}<extra></extra>"))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_tickformat=",.0f")
    st.plotly_chart(fig, theme="streamlit", config={"displayModeBar": False})
    st.caption(f"Data: {source}. NAV = TRS equity of USD 20m plus the interest margin earned since 1 Jan 2025.")

    st.subheader("Monthly P&L by source (USD)")
    # Categorical slots 1-5 in order (validated: neighbours stay apart, incl. colour-blind vision)
    PNL_COLORS = {"MMF and deposit income": "#2a78d6", "IC deposit interest paid": "#eb6834",
                  "IC loan interest earned": "#1baf7a", "FX revaluation": "#eda100", "FX deal MTM": "#e87ba4"}
    pnl = hist["pnl_daily"].copy()
    pnl["month"] = pd.to_datetime(pnl["pnl_date"]).dt.to_period("M").dt.to_timestamp()
    monthly = pnl.groupby(["month", "component"], as_index=False)["amount_usd"].sum()
    fig = go.Figure()
    for comp, color in PNL_COLORS.items():
        m = monthly[monthly["component"] == comp]
        fig.add_trace(go.Bar(x=m["month"], y=m["amount_usd"], name=comp, marker_color=color,
                             hovertemplate=f"{comp}<br>%{{x|%b %Y}}<br>USD %{{y:,.0f}}<extra></extra>"))
    net = monthly.groupby("month", as_index=False)["amount_usd"].sum()
    fig.add_trace(go.Scatter(x=net["month"], y=net["amount_usd"], name="Net P&L", mode="markers",
                             marker=dict(size=8, color="#52514e", symbol="diamond"),
                             hovertemplate="Net P&L<br>%{x|%b %Y}<br>USD %{y:,.0f}<extra></extra>"))
    fig.update_layout(barmode="relative", bargap=0.25, height=360, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis_tickformat=",.0f", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, theme="streamlit", config={"displayModeBar": False})
    st.caption("Income above zero, costs below; the diamond is the month's net P&L (= the change in NAV). "
               "MMF income falls with the central bank rate cuts. FX revaluation (the balance sheet in EUR, "
               "GBP and CHF moving with the rate) and FX deal MTM largely cancel: TRS keeps each currency "
               "flat. The latest month is not complete.")
    with st.expander("Monthly P&L table (USD)"):
        table = monthly.pivot(index="month", columns="component", values="amount_usd").reindex(
            columns=list(PNL_COLORS)).fillna(0.0)
        table["Net P&L"] = table.sum(axis=1)
        table.index = table.index.strftime("%b %Y")
        st.dataframe(table.iloc[::-1].round(0), width="stretch", column_config={
            c: st.column_config.NumberColumn(format="localized") for c in table.columns})

st.subheader("Group entities")
st.dataframe(data["entities"], hide_index=True, width="stretch")

iv = data["iv_commitments"]
st.subheader("IV commitments by currency")
by_ccy = iv.assign(uncalled=iv["commitment"] * (1 - iv["called_pct_at_start"])) \
    .groupby("currency")[["commitment", "uncalled"]].sum().reset_index()
st.dataframe(by_ccy, hide_index=True, column_config={
    "commitment": st.column_config.NumberColumn("Commitment", format="localized"),
    "uncalled": st.column_config.NumberColumn(f"Uncalled at {config.HISTORY_START:%d %b %Y}", format="localized"),
})
