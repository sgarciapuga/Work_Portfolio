import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import CCY_COLORS, as_of, config, no_history_message, page_header, results, static_data

page_header("Balance sheet & NAV", 1, "The TRS balance sheet in each currency and in USD, on the as-of date.")

hist, source = results()
if not hist:
    no_history_message()
    st.stop()

day = as_of()
static, _ = static_data()
cash = hist["cash_balance"]
cash = cash[(cash["balance_date"] == day) & cash["account_id"].isin(config.TRS_MAIN_ACCOUNT.values())]
val = hist["valuation"]
val = val[val["valuation_date"] == day]
ic = hist["ic_current_account"]
ic = ic[(ic["balance_date"] == day) & ((ic["closing"] != 0) | (ic["accrued_interest"] != 0))]
nav = hist["nav_daily"]
nav_day = nav[nav["nav_date"] == day].set_index("currency")

# One line per balance sheet item, in the item's currency (positive = asset, negative = liability)
lines = []
for r in cash.itertuples():
    lines.append({"item": "Bank cash", "detail": r.account_id, "currency": r.account_id[-3:], "amount": r.closing})
for r in val.itertuples():
    kind = "IC deposit from IV" if r.item_id.startswith("ICD-IV") else (
        "Bank deposit" if r.currency == "CHF" else "Money market fund")
    lines.append({"item": kind, "detail": f"{r.item_id} (incl. accrued {r.accrued_interest:,.0f})",
                  "currency": r.currency, "amount": r.value_ccy})
for r in ic.itertuples():
    owed = r.closing + r.accrued_interest
    lines.append({"item": "IC current account" + (" (entity owes TRS)" if owed < 0 else ""),
                  "detail": f"{r.entity_code} (incl. accrued {r.accrued_interest:,.0f})",
                  "currency": r.currency, "amount": -owed})
lines = pd.DataFrame(lines)

st.subheader(f"Summary on {day:%d %b %Y}")
summary = nav_day[["assets", "liabilities", "nav_ccy", "nav_usd", "open_fx_position_usd"]].reindex(config.CURRENCIES)
summary["within_tolerance"] = summary["open_fx_position_usd"].abs() <= config.FX_TOLERANCE_USD
st.dataframe(summary.reset_index(), hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="localized") for c in
    ["assets", "liabilities", "nav_ccy", "nav_usd", "open_fx_position_usd"]})
st.caption(f"Total NAV: USD {summary['nav_usd'].sum():,.0f}. Open FX = NAV in EUR, GBP or CHF "
           "(no FX deals until Phase 3); the tolerance is ±USD 50k per currency.")

ccy = st.radio("Currency", config.CURRENCIES, horizontal=True)
st.dataframe(lines[lines["currency"] == ccy].drop(columns="currency"), hide_index=True, width="stretch",
             column_config={"amount": st.column_config.NumberColumn(f"Amount ({ccy})", format="localized")})

st.subheader("Open FX position by currency (USD)")
fig = go.Figure()
for c in ["EUR", "GBP", "CHF"]:
    s = nav[nav["currency"] == c]
    fig.add_trace(go.Scatter(x=s["nav_date"], y=s["open_fx_position_usd"], name=c, mode="lines",
                             line=dict(width=2, color=CCY_COLORS[c]),
                             hovertemplate=f"{c}<br>%{{x|%d %b %Y}}<br>USD %{{y:,.0f}}<extra></extra>"))
for y in (config.FX_TOLERANCE_USD, -config.FX_TOLERANCE_USD):
    fig.add_hline(y=y, line=dict(width=1, dash="dash", color="#9AA0A6"))
fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), yaxis_tickformat=",.0f",
                  legend=dict(orientation="h", y=1.08), hovermode="x unified")
st.plotly_chart(fig, theme="streamlit", config={"displayModeBar": False})
st.caption(f"Dashed lines: ±USD {config.FX_TOLERANCE_USD:,.0f} tolerance. Data: {source}.")
