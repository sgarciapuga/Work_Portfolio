from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import as_of, config, market_data, money, no_history_message, page_header, results, static_data

from tsim.calendars import add_months, is_business_day
from tsim.engine import fx_daily
from tsim.rates import daily_rates
from tsim.whatif import compare, play, proposals, setup

CHART = {"displayModeBar": False}
PATH_COLORS = {"Autopilot": "#2a78d6", "Yours": "#eb6834"}   # categorical slots 1-2

page_header("Today", 1, "Play treasurer: take a day's decisions yourself and compare them with the autopilot.")

hist, source = results()
if not hist:
    no_history_message()
    st.stop()
last = max(hist["nav_daily"]["nav_date"])
start_of_day = as_of() or last
day = start_of_day + timedelta(days=1)
while not is_business_day(day, "USD"):
    day += timedelta(days=1)
replay = start_of_day < last

c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
c1.markdown(f"### {day:%A %d %B %Y}")
horizon = c2.radio("Compare over", ["1 week", "1 month"], index=1, horizontal=True)
until = day + timedelta(days=6) if horizon == "1 week" else add_months(day, 1, ["USD"]) - timedelta(days=1)
if replay:
    st.caption(f"Replay: you start from the close of {start_of_day:%d %b %Y} (the sidebar's as-of date) and the "
               "rates that really followed are used, so leaving FX open shows its real cost"
               + (f"; after {last:%d %b} rates are held." if until > last else "."))
else:
    st.caption(f"Today: you start from the close of {last:%d %b %Y}, the last closed day. Future rates are unknown, "
               f"so they are held at {last:%d %b}; the FX stress below shows the risk of a position left open.")


@st.cache_resource(max_entries=4, show_spinner="Rebuilding the history up to the start of the day...")
def base_engine(day, until, data_key):
    fx_rows, ir_rows, _ = market_data()
    static, _ = static_data()
    fx = fx_daily(fx_rows, config.HISTORY_START, until)
    on = daily_rates(ir_rows, config.HISTORY_START, until)
    return setup(static, on, fx, config.HISTORY_START, day, until), fx


base, fx = base_engine(day, until, (str(last), source))
props, auto_day = proposals(base, day)
ap = base.autopilot
prev = day - timedelta(days=1)

# ---------------- start of day ----------------
st.markdown("#### Start of day")
rows = []
for ccy in config.CURRENCIES:
    due = base.flows.loc[base.flows["value_date"] == day]
    flows_today = due.loc[due["currency"] == ccy, "amount"].sum()
    settling = sum(a for t in base.tickets if not t["is_internal"] and t["value_date"] == day
                   for c, a in base.ticket_legs(t) if c == ccy)
    rows.append({"Currency": ccy, "Bank cash": base.cash[ccy], "MMF / deposit": base.inv[ccy],
                 "Group flows due today": flows_today, "FX settling today": settling,
                 f"Lowest cash, next {config.LOOKAHEAD_BUSINESS_DAYS} days": ap.projected_low(prev, ccy),
                 "Open FX (USD)": 0.0 if ccy == "USD" else base.fx_position(ccy) / fx.loc[prev, ccy]})
st.dataframe(pd.DataFrame(rows).round(0), hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="localized") for c in rows[0] if c != "Currency"})
st.caption(f"Balances at the close of {prev:%d %b}. Lowest cash = bank cash plus the group flows and FX settlements of "
           f"the next {config.LOOKAHEAD_BUSINESS_DAYS} business days, before any investing; the MMF covers a dip. "
           f"Open FX tolerance: ±USD {config.FX_TOLERANCE_USD:,.0f} per currency.")

left, right = st.columns(2, gap="large")
with left:
    st.markdown("**Due today**")
    due = base.flows[base.flows["value_date"] == day]
    names = static_data()[0]["flow_codes"].set_index("flow_code")["description"]
    if due.empty:
        st.caption("No group flows.")
    for f in due.itertuples():
        st.markdown(f"- {f.entity_code} {'receives' if f.amount > 0 else 'pays'} {f.currency} {abs(f.amount):,.0f}: "
                    f"{names[f.flow_code].lower()}")
    for pid, p in base.terms.items():
        if p["status"] == "open" and p["maturity_date"] == day:
            st.markdown(f"- {pid} matures: {p['currency']} {p['principal']:,.0f} plus interest back on call")
with right:
    st.markdown("**Requests from the entities**")
    log = auto_day["activity"]
    requests = log[(log["kind"] == "action") & log["entity_code"].notna() & (log["category"] == "FX")]
    if requests.empty:
        st.caption("None today. At month end the service companies ask TRS for forwards to convert their foreign "
                   "currency.")
    for r in requests.itertuples():
        st.markdown(f"- {r.description}")
    iv = base.iv_dep + base.iv_accrued
    st.markdown(f"**IV buffer:** {money(iv)} (minimum {money(config.IV_BUFFER_USD)})")

# ---------------- decisions ----------------
st.markdown("#### Your decisions")
st.caption("The autopilot's proposal is filled in for each decision. Change an amount, or set it to 0 to skip it. "
           "Amounts are in the currency shown: + = TRS buys or invests, − = TRS sells or redeems. Only what is on this "
           "form happens on your day; the autopilot takes over again the next day.")
shown = props[(props["proposed"] != 0) | props["key"].str.startswith(("extra_spot", "invest"))]
with st.form(f"decisions-{day}"):
    values = {}
    for kind, group in shown.groupby("kind", sort=False):
        st.markdown(f"**{kind}**")
        for r in group.itertuples():
            a, b = st.columns([3, 1], vertical_alignment="center")
            a.markdown(r.label + (f"  \n<small>Autopilot: {r.proposed:+,.0f}. {r.reason}</small>"
                                  if isinstance(r.reason, str) else ""), unsafe_allow_html=True)
            values[r.key] = b.number_input(r.currency, value=float(r.proposed), step=10_000.0, format="%.0f",
                                           key=f"{day}-{r.key}", label_visibility="collapsed")
    submitted = st.form_submit_button("Run my day", type="primary")

state_key = f"played-{day}-{until}"
if submitted:
    overrides = {k: v for k, v in values.items()}
    st.session_state[state_key] = (overrides, play(base, day, until), play(base, day, until, overrides))
if state_key not in st.session_state:
    st.info("Take your decisions and press **Run my day** to see them next to the autopilot's.")
    st.stop()

overrides, auto, mine = st.session_state[state_key]
changed = {k: v for k, v in overrides.items()
           if abs(v - props.set_index("key")["proposed"].get(k, 0.0)) >= 0.5}

# ---------------- comparison ----------------
st.markdown(f"#### Your day against the autopilot's, {day:%d %b} to {until:%d %b}")
shock = st.slider("FX stress: move against TRS's open positions at the end of the day", 1, 10, 2, format="%d%%")
table = compare(auto, mine, fx, day, shock / 100)
t = table.set_index("Measure")
nav_diff = t.iloc[0]["Difference"]
risk = t.iloc[-1]
if not changed:
    st.success("You took the autopilot's decisions: the two days are the same.")
else:
    st.markdown(f"You changed {len(changed)} decision{'s' if len(changed) > 1 else ''}. By {until:%d %b} your NAV is "
                f"**USD {nav_diff:+,.0f}** against the autopilot's; with a {shock}% FX move, your open positions "
                f"would lose **USD {risk['Yours']:,.0f}** (autopilot: USD {risk['Autopilot']:,.0f}).")
st.dataframe(table.round(0), hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="localized") for c in ["Autopilot", "Yours", "Difference"]})
st.caption("Interest is the MMF, deposit and IC interest; FX is the balance sheet revaluation plus the deals' MTM. "
           "Idle cash = bank cash above the operating minimum, earning nothing. After your day the autopilot takes over "
           "on both sides, so a position you leave open is closed on the next business day.")

fig = go.Figure()
for name, res in [("Autopilot", auto), ("Yours", mine)]:
    nav = res["nav_daily"]
    s = nav[nav["currency"] != "USD"].assign(a=lambda x: x["open_fx_position_usd"].abs()).groupby("nav_date")["a"].sum()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines", line=dict(width=2, color=PATH_COLORS[name]),
                             hovertemplate=f"{name}<br>%{{x|%d %b}}<br>USD %{{y:,.0f}}<extra></extra>"))
fig.add_hline(y=config.FX_TOLERANCE_USD, line=dict(width=1, dash="dash", color="#9AA0A6"))
fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), yaxis_tickformat=",.0f", hovermode="x unified",
                  legend=dict(orientation="h", y=1.15))
st.plotly_chart(fig, theme="streamlit", config=CHART)
st.caption("Open FX positions, all three currencies added up (USD). Dashed line: the tolerance for one currency.")

a, b = st.columns(2, gap="large")
for col, name, res in [(a, "The autopilot's day", auto), (b, "Your day", mine)]:
    with col:
        st.markdown(f"**{name}**")
        lines = res["activity"]
        lines = lines[(lines["activity_date"] == day) & (lines["kind"] == "action")]
        if lines.empty:
            st.caption("No actions.")
        for r in lines.itertuples():
            st.markdown(f"- **{r.category}** · {r.description}")
            if isinstance(r.reason, str) and r.reason.startswith("Your"):
                st.caption(r.reason)
st.caption(f"Data: {source}.")
