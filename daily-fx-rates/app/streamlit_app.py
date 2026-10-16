"""FX rates report in Streamlit: a copy of the Google Data Studio report.

Run from the repository root:

    streamlit run daily-fx-rates/app/streamlit_app.py

Data comes from the fx_rates table in Neon PostgreSQL when DATABASE_URL is
available (Streamlit secrets, environment, or the root .env). Otherwise the
app reads the CSV backup in daily-fx-rates/data/.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fx_metrics import PAIRS, filter_period, moving_average, period_summary, rebased, to_pairs

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
CSV_PATH = APP_DIR.parent / "data" / "fx_rates.csv"

# Same colours as the Data Studio report (checked for colour-blind separation).
COLORS = {"GBP/USD": "#3B78E7", "EUR/USD": "#F08C2E", "GBP/EUR": "#00939E"}
REFERENCE_GREY = "#9AA0A6"
# Line charts grow with the screen height (see the .st-key-fx-chart-* CSS); this is the minimum.
CHART_HEIGHT = 380
CHART_CONFIG = {"displayModeBar": False, "responsive": True}
# Cards and the summary table keep a fixed width (narrower screens shrink or wrap them);
# only the line charts stretch with the screen.
KPI_CARD_WIDTH = 340
KPI_GAP = 16
SUMMARY_WIDTH = 3 * KPI_CARD_WIDTH + 2 * KPI_GAP  # lines up with the row of cards
TREND_COLORS = {"light": ("#1E8E3E", "#D93025"), "dark": ("#5BC97A", "#F28B82")}

# Data is reloaded once a day at this time. The pipeline stores the day's
# rates at 18:00 UTC, so they are always in the database by then.
REFRESH_TZ = ZoneInfo("Europe/London")
REFRESH_HOUR = 8


# ---------------------------------------------------------
# Data
# ---------------------------------------------------------
def _database_url():
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:  # no secrets.toml
        url = None
    if not url:
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO_ROOT / ".env")
        except ImportError:
            pass
        url = os.getenv("DATABASE_URL")
    return url


def refresh_key():
    """Date of the latest daily refresh. It changes once a day at REFRESH_HOUR UK time."""
    now = datetime.now(REFRESH_TZ)
    day = now.date() if now.hour >= REFRESH_HOUR else now.date() - timedelta(days=1)
    return day.isoformat()


# The cache is keyed on refresh_key(): when it changes at 08:00 the next visit
# reloads the data, and max_entries=1 drops the previous day's copy.
@st.cache_data(max_entries=1, show_spinner="Loading FX rates...")
def load_rates(refresh_day):
    """Return (rows, source label, loaded at). Falls back to the CSV if the database fails."""
    loaded_at = datetime.now(REFRESH_TZ)
    url = _database_url()
    if url:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
            query = text(
                "SELECT date, currency, fx_to_usd, fx_quality_flag "
                "FROM fx_rates WHERE currency IN ('EUR', 'GBP') ORDER BY date"
            )
            with engine.connect() as conn:
                rows = pd.read_sql(query, conn)
            return rows, "Neon PostgreSQL (fx_rates)", loaded_at
        except Exception as exc:
            source = f"CSV backup (database not available: {type(exc).__name__})"
            return pd.read_csv(CSV_PATH), source, loaded_at
    return pd.read_csv(CSV_PATH), "CSV backup (daily-fx-rates/data/fx_rates.csv)", loaded_at


# ---------------------------------------------------------
# Formatting
# ---------------------------------------------------------
def fmt_day(value, year=False):
    """'1 Jan' or '1 Jan 2026' (strftime has no portable day without zero padding)."""
    value = pd.Timestamp(value)
    return f"{value.day} {value:%b}" + (f" {value.year}" if year else "")


def fmt_pct(value):
    return "–" if pd.isna(value) else f"{value:+.2%}"


def section_title(text):
    st.markdown(f'<div class="fx-section">{text}</div>', unsafe_allow_html=True)


def pill(value):
    tone = "neutral" if pd.isna(value) or round(value, 4) == 0 else ("up" if value > 0 else "down")
    return f'<span class="fx-pill fx-{tone}">{fmt_pct(value)}</span>'


CSS = """
<style>
.block-container { padding: 2rem 2.5rem 1rem; max-width: none; }
@media (max-width: 640px) { .block-container { padding: 1.5rem 1rem 1rem; } }
/* Only the line charts grow: they take the screen height left after the rest of the page (about 670px). */
:root { --fx-chart-height: clamp(380px, calc(100vh - 670px), 900px); }
.st-key-fx-chart-rebased, .st-key-fx-chart-gbpeur { height: var(--fx-chart-height) !important; flex-basis: var(--fx-chart-height) !important; }
.st-key-fx-chart-rebased [data-testid="stFullScreenFrame"], .st-key-fx-chart-gbpeur [data-testid="stFullScreenFrame"],
.st-key-fx-chart-rebased .stPlotlyChart, .st-key-fx-chart-gbpeur .stPlotlyChart,
.st-key-fx-chart-rebased .js-plotly-plot, .st-key-fx-chart-gbpeur .js-plotly-plot { height: 100% !important; }
@media (max-width: 640px) { :root { --fx-chart-height: 380px; } }
.fx-subtitle { opacity: .75; margin-top: -.6rem; }
.fx-updated { text-align: right; opacity: .75; font-size: .9rem; margin-bottom: .25rem; }
.fx-pair { font-size: 1.1rem; opacity: .7; display: flex; align-items: center; gap: .45rem; }
.fx-dot { width: .7rem; height: .7rem; border-radius: 50%; display: inline-block; }
.fx-value { font-size: 2.4rem; font-weight: 500; line-height: 1.15; margin: .1rem 0 .5rem; font-variant-numeric: tabular-nums; }
.fx-changes { display: flex; flex-wrap: wrap; gap: .4rem 1.5rem; font-size: .9rem; padding-bottom: .9rem; }
.fx-section { font-size: 1.15rem; font-weight: 600; margin: .2rem 0 -.4rem; }
.fx-changes > span { opacity: .9; }
.fx-pill { padding: .15rem .45rem; border-radius: 4px; margin-right: .35rem; font-variant-numeric: tabular-nums; }
.fx-up { background: rgba(30,142,62,.14); color: var(--fx-up); }
.fx-down { background: rgba(217,48,37,.12); color: var(--fx-down); }
.fx-neutral { background: rgba(128,128,128,.15); }
</style>
"""


# ---------------------------------------------------------
# Charts
# ---------------------------------------------------------
def _base_layout(fig):
    fig.update_layout(
        autosize=True,
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False, tickformat="%-d %b", hoverformat="%a %-d %b %Y")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.2)", zeroline=False)
    return fig


def rebased_chart(period):
    indexed = rebased(period)
    fig = go.Figure()
    for pair in indexed.columns:
        fig.add_trace(
            go.Scatter(
                x=indexed.index,
                y=indexed[pair],
                name=pair,
                mode="lines",
                line=dict(color=COLORS[pair], width=2),
                customdata=period[pair],
                hovertemplate="%{y:.2f} (rate %{customdata:.4f})<extra>" + pair + "</extra>",
            )
        )
    fig.add_hline(y=100, line=dict(color=REFERENCE_GREY, width=1))
    return _base_layout(fig)


def gbpeur_chart(period):
    series = period["GBP/EUR"]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=series,
            name="GBP/EUR",
            mode="lines",
            line=dict(color=COLORS["GBP/EUR"], width=2),
            hovertemplate="%{y:.4f}<extra>GBP/EUR</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=moving_average(series),
            name="30-day average",
            mode="lines",
            line=dict(color=REFERENCE_GREY, width=1.5, dash="dash"),
            hovertemplate="%{y:.4f}<extra>30-day average</extra>",
        )
    )
    for label, value in (("High", series.max()), ("Low", series.min())):
        fig.add_hline(
            y=value,
            line=dict(color=REFERENCE_GREY, width=1, dash="dot"),
            annotation_text=f"{label} ({value:.4f})",
            annotation_position="top left" if label == "High" else "bottom left",
            annotation_font_size=11,
            annotation_bgcolor="rgba(128,128,128,.18)",
        )
    return _base_layout(fig)


# ---------------------------------------------------------
# Page
# ---------------------------------------------------------
st.set_page_config(page_title="FX rates", page_icon="💱", layout="wide")
# Up/down colours need lighter tones on the dark theme to stay readable.
UP, DOWN = TREND_COLORS["dark" if st.context.theme.type == "dark" else "light"]
st.markdown(CSS + f"<style>:root {{ --fx-up: {UP}; --fx-down: {DOWN}; }}</style>", unsafe_allow_html=True)

rows, source, loaded_at = load_rates(refresh_key())
pairs = to_pairs(rows)
if pairs.empty:
    st.error("No FX rates found.")
    st.stop()

first_day, last_day = pairs.index.min().date(), pairs.index.max().date()

header, controls = st.columns([3, 1], vertical_alignment="bottom")
with header:
    st.title("FX rates")
    st.markdown(
        '<p class="fx-subtitle">GBP vs EUR: performance against USD and the GBP/EUR rate.</p>',
        unsafe_allow_html=True,
    )
with controls:
    st.markdown(
        f'<div class="fx-updated">Latest rate: <b>{fmt_day(last_day, year=True)}</b></div>',
        unsafe_allow_html=True,
    )
    selected = st.date_input(
        "Period",
        value=(first_day, last_day),
        min_value=first_day,
        max_value=last_day,
        format="DD/MM/YYYY",
        label_visibility="collapsed",
    )

# While the user is picking, the date input holds only the start date.
start, end = (selected if len(selected) == 2 else (selected[0], last_day))
period = filter_period(pairs, start, end)
if len(period) < 2:
    st.warning("Pick a period of at least two days.")
    st.stop()

summary = period_summary(period)
since_label = f"since {fmt_day(period.index[0])}"

# KPI cards
kpi_row = st.container(horizontal=True, gap=KPI_GAP)
for pair in PAIRS:
    row = summary.loc[pair]
    with kpi_row.container(border=True, width=KPI_CARD_WIDTH):
        st.markdown(
            f"""
            <div class="fx-pair">{pair}<span class="fx-dot" style="background:{COLORS[pair]}"></span></div>
            <div class="fx-value">{row.latest:.4f}</div>
            <div class="fx-changes">
              <span>{pill(row.vs_previous_day)}vs previous day</span>
              <span>{pill(row.since_start)}{since_label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

# Charts
left, right = st.columns(2)
with left.container(border=True):
    section_title(f"GBP and EUR against USD (rebased, {fmt_day(period.index[0])} = 100)")
    st.plotly_chart(rebased_chart(period), width="stretch", height=CHART_HEIGHT, config=CHART_CONFIG, key="fx-chart-rebased")
with right.container(border=True):
    section_title("GBP/EUR with 30-day average")
    st.plotly_chart(gbpeur_chart(period), width="stretch", height=CHART_HEIGHT, config=CHART_CONFIG, key="fx-chart-gbpeur")

# Period summary
with st.container(border=True, width=SUMMARY_WIDTH):
    section_title("Period summary")
    since_column = f"Since {fmt_day(period.index[0])}"
    table = summary[["latest", "high", "low", "average", "since_start"]].rename(
        columns={
            "latest": "Latest",
            "high": "High",
            "low": "Low",
            "average": "Average",
            "since_start": since_column,
        }
    )
    styled = (
        table.style.format("{:.4f}", subset=["Latest", "High", "Low", "Average"])
        .format(fmt_pct, subset=[since_column])
        .map(lambda v: f"color: {UP if v > 0 else DOWN if v < 0 else 'inherit'}", subset=[since_column])
    )
    st.dataframe(styled, width="stretch")

st.caption(
    f"Rates from the Frankfurter API, stored daily by the GitHub Actions pipeline. "
    f"Weekends and holidays carry the last market rate. Source: {source}. "
    f"Loaded {loaded_at:%d %b %Y %H:%M} UK time (refreshes daily at {REFRESH_HOUR:02d}:00)."
)
