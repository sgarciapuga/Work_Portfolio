from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import as_of, config, market_data, money, no_history_message, page_header, results, tier_badge

CHART = {"displayModeBar": False}
LADDER_COLORS = {"IC term deposits": "#2a78d6", "FX deal settlements": "#eb6834"}   # categorical slots 1-2

page_header("Positions", 1, "Every open treasury position on the as-of date, valued daily.")

hist, source = results()
if not hist:
    no_history_message()
    st.stop()
deals, pos = hist["fx_deal"], hist["position"]
if "deal_type" not in deals.columns or "position_type" not in pos.columns:
    st.info("Positions arrive with the Phase 3 engine: run `python treasury-simulator/run_daily.py` "
            "or wait for the daily workflow.")
    st.stop()

day = as_of()
val = hist["valuation"]
val = val[val["valuation_date"] == day].set_index("item_id")
fx_rows, _, _ = market_data()
fx_rows = fx_rows.assign(date=pd.to_datetime(fx_rows["date"]).dt.date)
latest = fx_rows[fx_rows["date"] <= day].sort_values("date").groupby("currency")["fx_to_usd"].last()
usd_per = {c: 1.0 if c == "USD" else 1 / float(latest[c]) for c in config.CURRENCIES}   # USD per 1 unit

terms = pos[pos["position_id"].str.match(r"ICD-(?!IV)")]
terms = terms[(terms["start_date"] <= day) & (terms["maturity_date"] > day)]
terms = terms.assign(accrued=[-val["accrued_interest"].get(p, 0.0) for p in terms["position_id"]])
deals_open = deals[(deals["trade_date"] <= day) & (deals["value_date"] > day)]
deal_mtm = val[val["item_type"] == "fx_deal"]["mtm"]
mmf_ids = list(config.INVESTMENT_ACCOUNT.values())
mmf = val.loc[val.index.intersection(mmf_ids)]

# ---------------- tiles ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("MMFs and deposits (USD)", money(mmf["value_usd"].sum()))
term_usd = sum((r.principal + r.accrued) * usd_per[r.currency] for r in terms.itertuples())
c2.metric("IC term deposits (USD)", money(term_usd), f"{len(terms)} open", delta_color="off", delta_arrow="off")
c3.metric("Open FX deals", f"{deals_open['deal_id'].nunique()}",
          f"MTM USD {deal_mtm.sum():,.0f}", delta_color="off", delta_arrow="off")
upcoming = sorted([(r.maturity_date, r.position_id) for r in terms.itertuples()] +
                  [(r.value_date, r.deal_id) for r in deals_open.itertuples()])
c4.metric("Next maturity", f"{upcoming[0][0]:%d %b}" if upcoming else "None",
          upcoming[0][1] if upcoming else None, delta_color="off", delta_arrow="off")

# ---------------- MMFs ----------------
st.markdown(f"### Money market funds and deposits {tier_badge(1)}", unsafe_allow_html=True)
st.dataframe(pd.DataFrame({
    "Position": mmf.index, "Currency": mmf["currency"], "Value": mmf["value_ccy"],
    "of which accrued interest": mmf["accrued_interest"], "Value (USD)": mmf["value_usd"],
}), hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="localized") for c in ["Value", "of which accrued interest", "Value (USD)"]})
st.caption(f"Cash above the USD {config.OPERATING_MIN_USD:,.0f} operating minimum per currency goes into the MMF "
           "(a call deposit for CHF). MMF yield = overnight rate "
           f"{config.MMF_SPREAD_BP} bp; interest is paid on BD{config.MMF_INTEREST_PAY_BD} of the next month.")

# ---------------- IC term deposits ----------------
st.markdown(f"### IC term deposits {tier_badge(1)}", unsafe_allow_html=True)
if terms.empty:
    st.info(f"No IC term deposits open on {day:%d %b %Y}.")
else:
    st.dataframe(pd.DataFrame({
        "Deposit": terms["position_id"], "From": terms["counterparty"], "Currency": terms["currency"],
        "Principal": terms["principal"], "Fixed rate (%)": terms["rate"] * 100, "Start": terms["start_date"],
        "Maturity": terms["maturity_date"], "Days left": [(m - day).days for m in terms["maturity_date"]],
        "Accrued interest": terms["accrued"],
    }).sort_values("Maturity"), hide_index=True, width="stretch", column_config={
        "Principal": st.column_config.NumberColumn(format="localized"),
        "Accrued interest": st.column_config.NumberColumn(format="localized"),
        "Fixed rate (%)": st.column_config.NumberColumn(format="%.3f")})
st.caption("Each service company keeps its OPEX on call: about a month of outflows, on top of what its projected "
           "balance needs until the deposit matures. The rest goes into 3-month deposits, placed on the first "
           "business day of the month and at each maturity, so one matures most months (a ladder). Fixed rate = "
           f"MMF rate on the start date {config.IC_DEPOSIT_MARGIN_BP} bp + {config.IC_TERM_PREMIUM_BP} bp term "
           "premium; interest is paid at maturity. On-call balances earn MMF "
           f"{config.IC_DEPOSIT_MARGIN_BP} bp, floating.")

# ---------------- FX deal blotter ----------------
st.markdown(f"### FX deal blotter {tier_badge(1)}", unsafe_allow_html=True)
view = st.radio("Show", ["Traded in the last 3 months", f"Open on {day:%d %b %Y}"], horizontal=True)
shown = deals_open if view.startswith("Open") else deals[(deals["trade_date"] <= day) &
                                                         (deals["trade_date"] > day - timedelta(days=91))]
if shown.empty:
    st.info("No FX deals to show. The month-end forwards are booked "
            f"{config.FX_HEDGE_LOOKAHEAD_BD} business days before the last business day of the month.")
else:
    st.dataframe(pd.DataFrame({
        "Deal": shown["deal_id"], "Type": shown["deal_type"] + ["" if l == "single" else f" ({l})" for l in shown["leg"]],
        "Counterparty": [f"{c} (internal)" if i else f"{c} (bank)" for c, i in zip(shown["counterparty"],
                                                                                 shown["is_internal"])],
        "Trade date": shown["trade_date"], "Value date": shown["value_date"],
        "TRS buys": shown["buy_ccy"], "Buy amount": shown["buy_amount"],
        "TRS sells": shown["sell_ccy"], "Sell amount": shown["sell_amount"], "Rate": shown["rate"],
        "Status": ["open" if v > day else "settled" for v in shown["value_date"]],
        "MTM (USD)": [deal_mtm.get(d) if v > day else None for d, v in zip(shown["deal_id"], shown["value_date"])],
    }).sort_values(["Trade date", "Deal"], ascending=[False, True]), hide_index=True, width="stretch",
        column_config={**{c: st.column_config.NumberColumn(format="localized")
                          for c in ["Buy amount", "Sell amount", "MTM (USD)"]},
                       "Rate": st.column_config.NumberColumn(format="%.4f")})
st.caption("Deals from TRS's side. At month end each service company converts its foreign-currency balance into "
           "its own currency: it books an internal forward with TRS a few days ahead, TRS nets the internal deals "
           "and covers the net with one external forward per currency, so the two sides cancel. Rates are in "
           "market convention (EUR/USD, GBP/USD, USD/CHF, GBP/CHF). MTM = (today's forward for the value date − "
           "deal rate) × amount, undiscounted.")

# ---------------- maturity ladder ----------------
st.markdown(f"### Maturity ladder, next 13 weeks {tier_badge(1)}", unsafe_allow_html=True)
week0 = day - timedelta(days=day.weekday())
weeks = [week0 + timedelta(weeks=i) for i in range(13)]
events = [{"week": m - timedelta(days=m.weekday()), "type": "IC term deposits",
           "usd": (p + p * r * (m - s).days / config.DAY_COUNT_BASIS[c]) * usd_per[c]}
          for p, r, s, m, c in zip(terms["principal"], terms["rate"], terms["start_date"], terms["maturity_date"],
                                   terms["currency"])]
for r in deals_open.itertuples():
    ccy, amount = (r.buy_ccy, r.buy_amount) if r.buy_ccy != "USD" else (r.sell_ccy, r.sell_amount)
    events.append({"week": r.value_date - timedelta(days=r.value_date.weekday()), "type": "FX deal settlements",
                   "usd": amount * usd_per[ccy]})
ladder = pd.DataFrame(events, columns=["week", "type", "usd"])
ladder = ladder[ladder["week"] <= weeks[-1]].groupby(["week", "type"], as_index=False)["usd"].sum()
fig = go.Figure()
for kind, color in LADDER_COLORS.items():
    s = ladder[ladder["type"] == kind].set_index("week")["usd"].reindex(weeks, fill_value=0.0)
    fig.add_trace(go.Bar(x=[f"w/c {w:%d %b}" for w in weeks], y=s.values, name=kind, marker_color=color,
                         hovertemplate=f"{kind}<br>%{{x}}<br>USD %{{y:,.0f}}<extra></extra>"))
fig.update_layout(barmode="stack", bargap=0.3, height=300, margin=dict(l=10, r=10, t=10, b=10),
                  yaxis_tickformat=",.0f", legend=dict(orientation="h", y=1.12))
st.plotly_chart(fig, theme="streamlit", config=CHART)
with st.expander("Ladder table (USD)"):
    table = ladder.pivot(index="week", columns="type", values="usd").reindex(weeks).fillna(0.0).round(0)
    table.index = [f"w/c {w:%d %b %Y}" for w in table.index]
    st.dataframe(table, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="localized") for c in table.columns})
st.caption("What matures each week, in USD at the as-of date's rates: IC term deposits (principal plus interest, "
           "back on call) and FX deals settling (the EUR, GBP or CHF leg). Week commencing Monday. "
           f"Data: {source}.")
