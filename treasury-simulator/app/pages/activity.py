from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import as_of, config, money, no_history_message, page_header, results, static_data

KIND_COLORS = {"Treasurer's actions": "#2a78d6", "Scheduled events": "#eb6834"}   # categorical slots 1-2
KIND_OF = {"action": "Treasurer's actions", "event": "Scheduled events"}
PLAN_LABEL, PLAN_COLOR = "Planned (autopilot)", "#1baf7a"                         # categorical slot 3

page_header("Activity", 1, "The treasurer's log: what happened each day, what the autopilot decided and why.")

hist, source = results()
if not hist:
    no_history_message()
    st.stop()
act = hist.get("activity", pd.DataFrame())
if "description" not in act.columns or "cash_txn" not in hist:
    st.info("No treasurer's log loaded. If the app was just updated, reboot it (Manage app → Reboot app) so it "
            "loads the new tables; otherwise wait for the daily workflow.")
    st.stop()

day = as_of()
first, last = min(hist["nav_daily"]["nav_date"]), max(hist["nav_daily"]["nav_date"])
plan = hist.get("activity_plan", pd.DataFrame())
plan = plan[plan["activity_date"] > last] if "description" in plan.columns else plan.iloc[0:0]
action_days = sorted(set(act.loc[act["kind"] == "action", "activity_date"]))
prev_active = max((d for d in action_days if d < day), default=None)
# no later day with a decision: the button still reaches the latest simulated day
next_active = min((d for d in action_days if d > day), default=last if day < last else None)


def go_to(d):
    st.session_state["goto_day"] = min(max(d, first), last)   # the sidebar date stays inside the history


# ---------------- day navigation ----------------
c1, c2, c3, c4, c5 = st.columns([1.3, 1, 3, 1, 1.3], vertical_alignment="center")
c1.button("◀◀ Previous active day", on_click=go_to, args=(prev_active,), disabled=prev_active is None,
          width="stretch")
c2.button("◀ Day before", on_click=go_to, args=(day - timedelta(days=1),), disabled=day <= first, width="stretch")
c3.markdown(f"<h3 style='text-align:center;margin:0'>{day:%A %d %B %Y}</h3>" +
            ("<p style='text-align:center;margin:0;opacity:0.7'>Last closed day</p>" if day == last else ""),
            unsafe_allow_html=True)
c4.button("Day after ▶", on_click=go_to, args=(day + timedelta(days=1),), disabled=day >= last, width="stretch")
c5.button("Next active day ▶▶" if next_active != last or last in action_days else "Latest day ▶▶",
          on_click=go_to, args=(next_active,), disabled=next_active is None, width="stretch")

# ---------------- activity strip ----------------
plan_end = max(plan["activity_date"]) if len(plan) else last
start, end = max(first, day - timedelta(days=60)), min(plan_end, day + timedelta(days=30))
window = act[(act["activity_date"] >= start) & (act["activity_date"] <= end)]
days = pd.date_range(start, end).date
fig = go.Figure()
for kind, label in KIND_OF.items():
    counts = window[window["kind"] == kind].groupby("activity_date").size().reindex(days, fill_value=0)
    fig.add_trace(go.Bar(x=list(days), y=counts.values, name=label, marker_color=KIND_COLORS[label],
                         hovertemplate=f"%{{x|%a %d %b %Y}}<br>{label}: %{{y}}<extra></extra>"))
if len(plan) and end > last:
    counts = plan.groupby("activity_date").size().reindex(days, fill_value=0)
    fig.add_trace(go.Bar(x=list(days), y=counts.values, name=PLAN_LABEL, marker_color=PLAN_COLOR,
                         marker_pattern_shape="/",
                         hovertemplate=f"%{{x|%a %d %b %Y}}<br>{PLAN_LABEL}: %{{y}}<extra></extra>"))
fig.add_vline(x=day, line=dict(width=1, color="#52514e", dash="dot"))
fig.update_layout(barmode="stack", bargap=0.15, height=180, margin=dict(l=10, r=10, t=10, b=10),
                  legend=dict(orientation="h", y=1.25, traceorder="normal"), yaxis=dict(title=None, dtick=2),
                  xaxis_tickformat="%d %b")
event = st.plotly_chart(fig, theme="streamlit", config={"displayModeBar": False}, on_select="rerun",
                        selection_mode="points", key=f"strip-{day}")
picked = [p["x"] for p in (event.selection.points if event else [])]
if picked:
    target = min(max(pd.to_datetime(picked[0]).date(), first), last)   # a planned bar opens the latest day
    if target != day:
        go_to(target)
        st.rerun()
st.caption("Entries per day around the as-of date (dotted line); hatched bars are the autopilot's plan for the coming "
           "business days. Click a bar to open that day; the outer buttons skip to the previous or next day with a "
           "decision.")

# ---------------- the day ----------------
today = act[act["activity_date"] == day].sort_values("seq")
actions, events = today[today["kind"] == "action"], today[today["kind"] == "event"]
static, _ = static_data()
codes = static["flow_codes"].set_index("flow_code")
txn = hist["cash_txn"]
group_codes = set(codes.index[codes["category"] == "group_flows"])
flows = txn[(txn["value_date"] == day) & txn["flow_code"].isin(group_codes)] if "flow_code" in txn.columns \
    else txn.iloc[0:0]

parts = [f"{len(actions)} decision{'s' if len(actions) != 1 else ''}",
         f"{len(events)} scheduled event{'s' if len(events) != 1 else ''}",
         f"{len(flows)} group flow{'s' if len(flows) != 1 else ''}"]
if day.weekday() >= 5:
    st.info("Weekend: no payments and no dealing. Interest still accrues for the day.")
elif today.empty and flows.empty:
    st.info("A quiet day: no group flows, nothing scheduled and nothing for the treasurer to do.")
else:
    st.markdown(f"**{', '.join(parts)}.**")

# ---------------- the plan (latest day only) ----------------
if day == last and len(plan):
    def plan_lines(rows):
        for r in rows.itertuples():
            tag = "Will do" if r.kind == "action" else ("Due" if r.category == "Group flows" else "Scheduled")
            st.markdown(f"- *{tag}* · **{r.category}** · {r.description}")
            if isinstance(r.reason, str):
                st.caption(f"Why: {r.reason}")

    today_date = last + timedelta(days=1)   # the engine runs to yesterday: overnight rates come out the next day
    by_day = dict(tuple(plan.sort_values(["activity_date", "seq"]).groupby("activity_date")))
    with st.container(border=True):
        st.markdown(f"#### Today, {today_date:%A %d %B}: to do")
        st.caption(f"Based on the closing position of {last:%d %b}. What the autopilot would do today, from the known "
                   f"schedule and holding the FX and interest rates of {last:%d %b}.")
        if today_date in by_day:
            plan_lines(by_day[today_date])
        else:
            st.markdown("Nothing to do today" + (" (weekend)." if today_date.weekday() >= 5 else "."))
        later = {d: rows for d, rows in by_day.items() if d > today_date}
        if later:
            st.markdown("#### Next days")
            st.caption(f"The look-ahead to {max(later):%a %d %b}: planned again every evening, so these actions can "
                       "change when rates move or new flows appear.")
            for d, rows in later.items():
                st.markdown(f"**{d:%A %d %B}**")
                plan_lines(rows)
elif day == last:
    st.caption("No plan yet: it arrives with the next engine run.")

left, right = st.columns(2, gap="large")
with left:
    st.markdown("#### Treasurer's actions")
    if actions.empty:
        st.caption("No decisions needed.")
    for r in actions.itertuples():
        st.markdown(f"**{r.category}** · {r.description}")
        if isinstance(r.reason, str):
            st.caption(f"Why: {r.reason}")
with right:
    st.markdown("#### Scheduled events")
    if events.empty:
        st.caption("Nothing settled, matured or paid.")
    for r in events.itertuples():
        st.markdown(f"**{r.category}** · {r.description}")

st.markdown("#### Group flows")
if flows.empty:
    st.caption("No fees, payroll or other group flows today.")
else:
    st.dataframe(pd.DataFrame({
        "Entity": flows["account_id"].str.split("-").str[0],
        "Flow": [codes.loc[c, "description"] for c in flows["flow_code"]],
        "Counterparty": flows["counterparty"], "Currency": flows["currency"], "Amount": flows["amount"],
    }), hide_index=True, width="stretch", column_config={"Amount": st.column_config.NumberColumn(format="localized")})
    net = flows.groupby("currency")["amount"].sum()
    st.caption("Each entity settles its flows with TRS the same day through its IC current account (the in-house "
               "bank), so they land on TRS's bank accounts: net " +
               ", ".join(f"{c} {v:+,.0f}" for c, v in net.items()) + ".")

# ---------------- end of day ----------------
st.markdown("#### End of day")
nav = hist["nav_daily"]
nav_day = nav[nav["nav_date"] == day].set_index("currency")
open_fx = nav_day.drop(index="USD")["open_fx_position_usd"]
worst = open_fx.abs().idxmax()
alerts = hist["alerts"]
alerts_day = alerts[alerts["alert_date"] == day] if "alert" in alerts.columns else alerts.iloc[0:0]
val = hist["valuation"]
iv = -val[(val["valuation_date"] == day) & val["item_id"].astype(str).str.startswith("ICD-IV")]["value_usd"].sum()
pnl = hist["pnl_daily"]
pnl_day = pnl[pnl["pnl_date"] == day]["amount_usd"].sum()
m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Largest open FX: {worst}", money(open_fx[worst]),
          "Within tolerance" if abs(open_fx[worst]) <= config.FX_TOLERANCE_USD else "Outside tolerance",
          delta_color="off", delta_arrow="off")
m2.metric("Alerts", f"{len(alerts_day)}", ", ".join(alerts_day["alert"]) if len(alerts_day) else "None",
          delta_color="off", delta_arrow="off")
m3.metric("IV buffer at TRS", money(iv), f"Minimum {money(config.IV_BUFFER_USD)}", delta_color="off",
          delta_arrow="off")
m4.metric("Today's P&L (USD)", f"{pnl_day:+,.0f}", "= change in NAV", delta_color="off", delta_arrow="off")
st.caption(f"Data: {source}.")
