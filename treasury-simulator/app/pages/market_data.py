from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import CCY_COLORS, as_of, config, market_data, page_header, tier_badge

from tsim.market import (PAIRS, TENORS, differentials_bp, forward_points_history, implied_forwards,
                         market_quotes)
from tsim.rates import daily_rates

PAIR_COLORS = {"EUR/USD": CCY_COLORS["EUR"], "GBP/USD": CCY_COLORS["GBP"], "USD/CHF": CCY_COLORS["CHF"]}
INDEX_NAMES = {"USD": "SOFR", "EUR": "€STR", "GBP": "SONIA", "CHF": "SARON"}
CHART = {"displayModeBar": False}

page_header("Market data", 1, "FX rates and overnight interest rates used by the simulator, "
            "and what they mean for FX forwards.")

fx_rows, ir_rows, source = market_data()
if fx_rows.empty or ir_rows.empty:
    st.info("No market data yet. Run `python treasury-simulator/run_daily.py --fetch-rates` from the repository root.")
    st.stop()

quotes = market_quotes(fx_rows)
last_fx = quotes.index.max()
end = min(as_of() or last_fx, last_fx)
start_all = max(quotes.index.min(), config.HISTORY_START - timedelta(days=10))
on = daily_rates(ir_rows, start_all, end)

period = st.radio("Period", ["3M", "6M", "YTD", "1Y", "All"], index=3, horizontal=True)
start = {"3M": end - timedelta(days=91), "6M": end - timedelta(days=182), "YTD": end.replace(month=1, day=1),
         "1Y": end - timedelta(days=365), "All": start_all}[period]
start = max(start, start_all)
q = quotes.loc[start:end]
market_days = q[q["is_raw"]]
r = on.loc[start:end]


def line_chart(df, cols, colors, names=None, fmt=",.4f", suffix="", height=300, ref=None):
    fig = go.Figure()
    for c in cols:
        name = (names or {}).get(c, c)
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=name, mode="lines",
                                 line=dict(width=2, color=colors[c]),
                                 hovertemplate=f"{name}<br>%{{x|%d %b %Y}}<br>%{{y:{fmt}}}{suffix}<extra></extra>"))
    if ref is not None:
        fig.add_hline(y=ref, line=dict(width=1, color="#9AA0A6"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), showlegend=len(cols) > 1,
                      legend=dict(orientation="h", y=1.12), hovermode="x unified", yaxis_tickformat=fmt)
    return fig


# ---------------- FX ----------------
st.markdown(f"### FX rates {tier_badge(1)}", unsafe_allow_html=True)
cols = st.columns(3)
for col, pair in zip(cols, PAIRS):
    first, last = market_days[pair].iloc[0], market_days[pair].iloc[-1]
    col.metric(pair, f"{last:.4f}", f"{last / first - 1:+.2%} over {period}", delta_color="off")
    col.plotly_chart(line_chart(market_days, [pair], PAIR_COLORS, height=220), theme="streamlit",
                     config=CHART, key=f"fx-{pair}")
st.caption("Market convention: EUR/USD and GBP/USD are USD per 1 EUR / GBP; USD/CHF is CHF per 1 USD. "
           "Charts show market days only (weekend and holiday rates are carried from the last market day). "
           f"Latest rate: {last_fx:%d %b %Y}.")

# ---------------- Overnight rates ----------------
st.markdown(f"### Overnight interest rates {tier_badge(2)}", unsafe_allow_html=True)
pct = r * 100
st.plotly_chart(line_chart(pct, config.CURRENCIES, CCY_COLORS, names={c: f"{INDEX_NAMES[c]} ({c})" for c in
                                                                     config.CURRENCIES},
                           fmt=".2f", suffix="%", height=320, ref=0), theme="streamlit", config=CHART)
latest = pd.DataFrame({
    "Index": [INDEX_NAMES[c] for c in config.CURRENCIES], "Currency": config.CURRENCIES,
    f"Rate on {end:%d %b %Y} (%)": [r[c].iloc[-1] * 100 for c in config.CURRENCIES],
    f"Change over {period} (bp)": [(r[c].iloc[-1] - r[c].iloc[0]) * 10_000 for c in config.CURRENCIES],
    "MMF yield (%)": [(r[c].iloc[-1] + config.MMF_SPREAD_BP / 10_000) * 100 for c in config.CURRENCIES],
})
st.dataframe(latest, hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="%.3f") for c in latest.columns if "%" in c} | {
    f"Change over {period} (bp)": st.column_config.NumberColumn(format="%+.0f")})
st.caption("Daily risk-free overnight rates from the New York Fed, ECB, Bank of England and SNB. "
           f"The simulator's MMFs yield the overnight rate {config.MMF_SPREAD_BP} bp.")

# ---------------- Differentials ----------------
st.markdown(f"### Rate differential against USD {tier_badge(3)}", unsafe_allow_html=True)
diff = differentials_bp(r)
st.plotly_chart(line_chart(diff, ["EUR", "GBP", "CHF"], CCY_COLORS,
                           names={c: f"{INDEX_NAMES[c]} − SOFR" for c in ["EUR", "GBP", "CHF"]},
                           fmt=",.0f", suffix=" bp", height=300, ref=0), theme="streamlit", config=CHART)
st.caption("Overnight rate minus SOFR, in basis points. Below zero, the currency pays less interest than USD: "
           "it trades at a forward premium against USD, so the forward points go in its favour.")

# ---------------- Forward points ----------------
st.markdown(f"### Implied FX forwards {tier_badge(3)}", unsafe_allow_html=True)
fwd = implied_forwards(quotes, on, end)
table = pd.DataFrame({
    "Pair": fwd["pair"], "Spot": fwd["spot"],
    "1M forward": fwd["fwd_1M"], "1M points": fwd["points_1M"],
    "3M forward": fwd["fwd_3M"], "3M points": fwd["points_3M"],
})
st.dataframe(table, hide_index=True, width="stretch", column_config={
    **{c: st.column_config.NumberColumn(format="%.4f") for c in ["Spot", "1M forward", "3M forward"]},
    **{c: st.column_config.NumberColumn(format="%+.1f") for c in ["1M points", "3M points"]}})
st.latex(r"F = S \times \frac{1 + r_{quote} \times \frac{d}{basis_{quote}}}{1 + r_{base} \times \frac{d}{basis_{base}}}"
         r"\qquad \text{points} = (F - S) \times 10{,}000")
st.caption(f"Spot and overnight rates on {end:%d %b %Y}; 1M = {TENORS['1M']} days, 3M = {TENORS['3M']} days. "
           "The overnight rate stands in for the 1M / 3M rate: a simplification to show the mechanics, "
           "not a dealing price. Positive points: the forward is above spot.")
hist = forward_points_history(quotes.loc[start:end], on, "3M")
st.plotly_chart(line_chart(hist, list(PAIRS), PAIR_COLORS, fmt=",.1f", suffix=" pips", height=300, ref=0),
                theme="streamlit", config=CHART, key="fwd-history")
st.caption(f"3M forward points over the period. Data: {source}.")
