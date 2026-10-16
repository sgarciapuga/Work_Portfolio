"""FX rates report in Streamlit, based on the Google Data Studio report.

Two pages share the header (latest rate and period picker) and footer:
- Overview: GBP and EUR against USD, the GBP/EUR rate, KPI cards and a period summary.
- Against GBP & EUR: EUR and USD against GBP, GBP and USD against EUR, and the
  EUR/USD and GBP/USD rates.

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

from fx_metrics import (
    PAIRS,
    PERIOD_PRESETS,
    filter_period,
    moving_average,
    period_csv,
    period_summary,
    preset_start,
    priced_in,
    rebased,
    to_pairs,
)
from story import period_story

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
CSV_PATH = APP_DIR.parent / "data" / "fx_rates.csv"

# One colour per pair, the same on every chart and card. The first three match
# the Data Studio report. Checked for colour-blind separation: the two lines that
# share a chart are always far apart; across charts, end labels and titles name each pair.
COLORS = {
    "GBP/USD": "#3B78E7",  # blue
    "EUR/USD": "#F08C2E",  # orange
    "GBP/EUR": "#00939E",  # teal
    "EUR/GBP": "#9E7B00",  # gold
    "USD/GBP": "#4A3AA7",  # violet
    "USD/EUR": "#C2185B",  # crimson
}
# The violet is too dark on the dark theme; a lighter step that stays apart from the blue.
DARK_COLORS = {"USD/GBP": "#AC72DA"}
REFERENCE_GREY = "#9AA0A6"
# Line charts grow with the screen height (see chart_height_css); this is the minimum.
CHART_HEIGHT = 380
CHART_CONFIG = {"displayModeBar": False, "responsive": True}
# Cards and the summary table keep a fixed width (narrower screens shrink or wrap them);
# only the line charts stretch with the screen.
KPI_CARD_WIDTH = 360  # fits both changes on one line, whatever the start date
KPI_GAP = 16
SUMMARY_WIDTH = 3 * KPI_CARD_WIDTH + 2 * KPI_GAP  # lines up with the row of cards
DATE_PICKER_WIDTH = 260
TREND_COLORS = {"light": ("#1E8E3E", "#D93025"), "dark": ("#5BC97A", "#F28B82")}
DEFAULT_PRESET = "YTD"

# Data is reloaded once a day at this time. The pipeline stores the day's
# rates at 18:00 UTC, so they are always in the database by then.
REFRESH_TZ = ZoneInfo("Europe/London")
REFRESH_HOUR = 8
# Normally the latest rate is yesterday's; older than this means the pipeline missed runs.
STALE_AFTER_DAYS = 2
FILLED_NOTE = "Weekend or holiday: last market rate"


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


def pill(value, inline=False):
    tone = "neutral" if pd.isna(value) or round(value, 4) == 0 else ("up" if value > 0 else "down")
    extra = " fx-inline" if inline else ""
    return f'<span class="fx-pill fx-{tone}{extra}">{fmt_pct(value)}</span>'


# ---------------------------------------------------------
# Styles
# ---------------------------------------------------------
# Chart keys per page. Each chart's wrapper gets the class st-key-<key>, which is
# how the CSS below resizes only the line charts.
OVERVIEW_CHARTS = ["fx-chart-rebased", "fx-chart-gbpeur"]
OTHER_BASES_CHARTS = ["fx-chart-gbp-base", "fx-chart-eur-base", "fx-chart-eurusd", "fx-chart-gbpusd"]


def chart_height_css(keys, variable, height):
    """CSS that sizes the charts with these keys to ``height``.

    Streamlit sizes the wrapper with flex-basis, so it is overridden together with height.
    (No '*' selectors: st.markdown would read them as Markdown emphasis.)
    """
    wrappers = ", ".join(f".st-key-{key}" for key in keys)
    inner = ", ".join(
        f".st-key-{key} {part}"
        for key in keys
        for part in ('[data-testid="stFullScreenFrame"]', ".stPlotlyChart", ".js-plotly-plot")
    )
    return (
        f":root {{ {variable}: {height}; }}\n"
        f"{wrappers} {{ height: var({variable}) !important; flex-basis: var({variable}) !important; }}\n"
        f"{inner} {{ height: 100% !important; }}\n"
    )


CSS = (
    "<style>\n"
    # Top padding clears the app bar that holds the page links.
    ".block-container { padding: 3.5rem 2.5rem 1rem; max-width: none; }\n"
    "@media (max-width: 640px) { .block-container { padding: 3.5rem 1rem 1rem; } }\n"
    # Overview: the charts take the screen height left after the rest of the page (about 714px).
    + chart_height_css(OVERVIEW_CHARTS, "--fx-chart-height", "clamp(380px, calc(100vh - 714px), 900px)")
    # Against GBP & EUR: two rows of charts share the height left after the header and footer.
    + chart_height_css(OTHER_BASES_CHARTS, "--fx-grid-height", "clamp(340px, calc((100vh - 409px) / 2), 700px)")
    + """@media (max-width: 640px) { :root { --fx-chart-height: 380px; --fx-grid-height: 340px; } }
.fx-subtitle { opacity: .75; margin-top: -.6rem; }
.fx-updated { text-align: right; opacity: .75; font-size: .9rem; margin-bottom: .25rem; }
.fx-pair { font-size: 1.1rem; opacity: .7; display: flex; align-items: center; gap: .45rem; }
.fx-dot { width: .7rem; height: .7rem; border-radius: 50%; display: inline-block; }
.fx-value { font-size: 2.4rem; font-weight: 500; line-height: 1.15; margin: .1rem 0 .5rem; font-variant-numeric: tabular-nums; }
.fx-changes { display: flex; flex-wrap: wrap; gap: .4rem 1rem; font-size: .9rem; padding-bottom: .9rem; }
.fx-section { font-size: 1.15rem; font-weight: 600; margin: .2rem 0 -.4rem; }
.fx-changes > span { opacity: .9; white-space: nowrap; }
.fx-pill { padding: .15rem .45rem; border-radius: 4px; margin-right: .35rem; font-variant-numeric: tabular-nums; }
.fx-up { background: rgba(30,142,62,.14); color: var(--fx-up); }
.fx-down { background: rgba(217,48,37,.12); color: var(--fx-down); }
.fx-neutral { background: rgba(128,128,128,.15); }
.fx-inline { margin-right: 0; padding: .05rem .35rem; white-space: nowrap; }
/* "In brief" fills the row beside the KPI cards, or takes its own row when there is no room.
   The row item is the wrapper around the keyed block, hence :has(). The row stretches its
   items so the story and the KPI cards share one height. */
.st-key-fx-kpi-row { align-items: stretch !important; }
[data-testid="stLayoutWrapper"]:has(> .st-key-fx-story) { flex: 1 1 420px !important; min-width: min(420px, 100%) !important; }
.fx-story-label { font-size: .75rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; opacity: .6; }
.fx-story-headline { font-size: 1.15rem; font-weight: 600; line-height: 1.3; margin: .15rem 0 .4rem; }
.fx-story-text { font-size: .92rem; line-height: 1.6; margin: 0 0 .5rem; opacity: .9; }
</style>
"""
)


# ---------------------------------------------------------
# Charts
# ---------------------------------------------------------
def _base_layout(fig, dates):
    fig.update_layout(
        autosize=True,
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified",
        # No legends: lines are labelled at their end, and rate charts name the rate in
        # the title (the dashed line is the 30-day average).
        showlegend=False,
    )
    # Pin the x-axis to the period: Plotly pads it when a chart has markers.
    fig.update_xaxes(
        showgrid=False, tickformat="%-d %b", hoverformat="%a %-d %b %Y", range=[dates[0], dates[-1]]
    )
    fig.update_yaxes(gridcolor="rgba(128,128,128,.2)", zeroline=False)
    return fig


def _filled_notes(is_raw):
    """Tooltip line for weekends and holidays (rate carried from the last market day).

    Added to the last trace's own tooltip text: a separate trace would be pulled
    into the unified tooltip on nearby market days too.
    """
    return ["" if raw else "<br>" + FILLED_NOTE for raw in is_raw]


def performance_chart(prices, is_raw):
    """Each column (a pair such as EUR/GBP) rebased to 100 on the first day, labelled at its end."""
    indexed = rebased(prices, prices.columns)
    notes = _filled_notes(is_raw)
    fig = go.Figure()
    for i, pair in enumerate(indexed.columns):
        color = COLORS[pair]
        last = i == len(indexed.columns) - 1
        fig.add_trace(
            go.Scatter(
                x=indexed.index,
                y=indexed[pair],
                name=pair,
                mode="lines",
                line=dict(color=color, width=2),
                customdata=list(zip(prices[pair], notes if last else [""] * len(notes))),
                hovertemplate="%{y:.2f} (rate %{customdata[0]:.4f})%{customdata[1]}<extra>" + pair + "</extra>",
            )
        )
        # End marker in the line colour; the label beside it stays in the text colour.
        fig.add_trace(
            go.Scatter(
                x=indexed.index[-1:],
                y=indexed[pair].iloc[-1:],
                mode="markers",
                marker=dict(color=color, size=8),
                cliponaxis=False,  # the dot sits on the right edge of the plot
                showlegend=False,
                hoverinfo="skip",
            )
        )

    # Label each line at its last point. When the two ends are close, push the
    # labels apart so they don't overlap.
    ends = indexed.iloc[-1].sort_values(ascending=False)
    span = indexed.max().max() - indexed.min().min()
    close = span > 0 and (ends.iloc[0] - ends.iloc[-1]) < span * 0.06
    for rank, (pair, value) in enumerate(ends.items()):
        fig.add_annotation(
            x=indexed.index[-1],
            y=value,
            text=f"{pair} {value:.1f}",
            showarrow=False,
            xanchor="left",
            xshift=8,
            yshift=(9 if rank == 0 else -9) if close else 0,
            font=dict(size=12),
        )

    fig.add_hline(y=100, line=dict(color=REFERENCE_GREY, width=1))
    _base_layout(fig, indexed.index)
    fig.update_layout(margin=dict(r=100))  # room for the end labels
    return fig


def rate_chart(series, pair, is_raw):
    """A rate with its 30-day average and the period high and low (with their dates)."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=series,
            name=pair,
            mode="lines",
            line=dict(color=COLORS[pair], width=2),
            hovertemplate="%{y:.4f}<extra>" + pair + "</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=moving_average(series),
            name="30-day average",
            mode="lines",
            line=dict(color=REFERENCE_GREY, width=1.5, dash="dash"),
            customdata=_filled_notes(is_raw),
            hovertemplate="%{y:.4f}%{customdata}<extra>30-day average</extra>",
        )
    )
    for label, day in (("High", series.idxmax()), ("Low", series.idxmin())):
        value = series[day]
        fig.add_hline(
            y=value,
            line=dict(color=REFERENCE_GREY, width=1, dash="dot"),
            annotation_text=f"{label} {value:.4f} on {fmt_day(day)}",
            annotation_position="top left" if label == "High" else "bottom left",
            annotation_font_size=11,
            annotation_bgcolor="rgba(128,128,128,.18)",
        )
    return _base_layout(fig, series.index)


def chart_card(column, title, fig, key):
    with column.container(border=True):
        section_title(title)
        st.plotly_chart(fig, width="stretch", height=CHART_HEIGHT, config=CHART_CONFIG, key=key)


# ---------------------------------------------------------
# Pages (they read `period`, `summary` and `since_label`, set below before nav.run())
# ---------------------------------------------------------
def overview_page():
    # KPI cards
    kpi_row = st.container(horizontal=True, gap=KPI_GAP, key="fx-kpi-row")
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

    # In brief: a written summary of the period, rebuilt from the same figures on every run.
    story_title, sentences = period_story(period, summary, fmt=lambda change: pill(change, inline=True))
    with kpi_row.container(border=True, key="fx-story"):
        st.markdown(
            f"""
            <div class="fx-story-label">In brief</div>
            <div class="fx-story-headline">{story_title}</div>
            <p class="fx-story-text">{" ".join(sentences)}</p>
            """,
            unsafe_allow_html=True,
        )

    # Charts
    left, right = st.columns(2)
    chart_card(left, f"GBP and EUR against USD (rebased, {start_label} = 100)",
               performance_chart(priced_in(period, "USD"), period["is_raw"]), "fx-chart-rebased")
    chart_card(right, "GBP/EUR with 30-day average", rate_chart(period["GBP/EUR"], "GBP/EUR", period["is_raw"]), "fx-chart-gbpeur")

    # Period summary
    with st.container(border=True, width=SUMMARY_WIDTH):
        section_title("Period summary")
        since_column = f"Since {start_label}"
        table = summary[["latest", "high", "high_date", "low", "low_date", "average", "since_start"]].rename(
            columns={
                "latest": "Latest",
                "high": "High",
                "high_date": "High on",
                "low": "Low",
                "low_date": "Low on",
                "average": "Average",
                "since_start": since_column,
            }
        )
        styled = (
            table.style.format("{:.4f}", subset=["Latest", "High", "Low", "Average"])
            .format(fmt_day, subset=["High on", "Low on"])
            .format(fmt_pct, subset=[since_column])
            .map(lambda v: f"color: {UP if v > 0 else DOWN if v < 0 else 'inherit'}", subset=[since_column])
        )
        st.dataframe(styled, width="stretch")


def other_bases_page():
    top_left, top_right = st.columns(2)
    chart_card(top_left, f"EUR and USD against GBP (rebased, {start_label} = 100)",
               performance_chart(priced_in(period, "GBP"), period["is_raw"]), "fx-chart-gbp-base")
    chart_card(top_right, f"GBP and USD against EUR (rebased, {start_label} = 100)",
               performance_chart(priced_in(period, "EUR"), period["is_raw"]), "fx-chart-eur-base")

    bottom_left, bottom_right = st.columns(2)
    chart_card(bottom_left, "EUR/USD with 30-day average", rate_chart(period["EUR/USD"], "EUR/USD", period["is_raw"]), "fx-chart-eurusd")
    chart_card(bottom_right, "GBP/USD with 30-day average", rate_chart(period["GBP/USD"], "GBP/USD", period["is_raw"]), "fx-chart-gbpusd")


PAGES = {
    "Overview": (overview_page, "overview", "GBP vs EUR: performance against USD and the GBP/EUR rate."),
    "Against GBP & EUR": (
        other_bases_page,
        "against-gbp-eur",
        "EUR and USD against GBP, GBP and USD against EUR, and the EUR/USD and GBP/USD rates.",
    ),
}


# ---------------------------------------------------------
# App
# ---------------------------------------------------------
st.set_page_config(page_title="FX rates", page_icon="💱", layout="wide")
# Up/down colours (and the violet) need lighter tones on the dark theme to stay readable.
DARK = st.context.theme.type == "dark"
UP, DOWN = TREND_COLORS["dark" if DARK else "light"]
if DARK:
    COLORS.update(DARK_COLORS)
st.markdown(CSS + f"<style>:root {{ --fx-up: {UP}; --fx-down: {DOWN}; }}</style>", unsafe_allow_html=True)

nav = st.navigation(
    [
        st.Page(page, title=title, url_path=url_path, default=(title == "Overview"))
        for title, (page, url_path, _) in PAGES.items()
    ],
    position="top",
)

rows, source, loaded_at = load_rates(refresh_key())
pairs = to_pairs(rows)
if pairs.empty:
    st.error("No FX rates found.")
    st.stop()

first_day, last_day = pairs.index.min().date(), pairs.index.max().date()

# Quick periods: while one is selected it sets the date picker (and follows new
# data); picking dates by hand clears it.
if "preset" not in st.session_state:
    st.session_state.preset = DEFAULT_PRESET
if st.session_state.preset:
    st.session_state.period = (preset_start(st.session_state.preset, first_day, last_day), last_day)


def _clear_preset():
    st.session_state.preset = None


# Shared header: the period controls keep their values when switching pages.
header, controls = st.columns(2, vertical_alignment="bottom")
with header:
    st.title("FX rates")
    st.markdown(f'<p class="fx-subtitle">{PAGES[nav.title][2]}</p>', unsafe_allow_html=True)
with controls.container(horizontal_alignment="right"):
    st.markdown(
        f'<div class="fx-updated">Latest rate: <b>{fmt_day(last_day, year=True)}</b></div>',
        unsafe_allow_html=True,
    )
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
        st.segmented_control("Quick period", PERIOD_PRESETS, key="preset", label_visibility="collapsed")
        selected = st.date_input(
            "Period",
            min_value=first_day,
            max_value=last_day,
            format="DD/MM/YYYY",
            label_visibility="collapsed",
            width=DATE_PICKER_WIDTH,
            key="period",
            on_change=_clear_preset,
        )
        download_slot = st.empty()  # filled below, once the period is known

age_days = (datetime.now(REFRESH_TZ).date() - last_day).days
if age_days > STALE_AFTER_DAYS:
    st.warning(
        f"The latest rate is from {fmt_day(last_day, year=True)} ({age_days} days ago). "
        "The daily update may have failed, so these figures may be out of date.",
        icon="⚠️",
    )

# While the user is picking, the date input holds only the start date.
start, end = (selected if len(selected) == 2 else (selected[0], last_day))
period = filter_period(pairs, start, end)
if len(period) < 2:
    st.warning("Pick a period of at least two days.")
    st.stop()

summary = period_summary(period)
start_label = fmt_day(period.index[0])
since_label = f"since {start_label}"

first, last = period.index[0], period.index[-1]
download_slot.download_button(
    "CSV",
    data=period_csv(period),
    file_name=f"fx_rates_{first:%Y-%m-%d}_{last:%Y-%m-%d}.csv",
    mime="text/csv",
    icon=":material/download:",
    help="Download the rates for the selected period",
    on_click="ignore",
)

nav.run()

st.caption(
    f"Rates from the Frankfurter API, stored daily by the GitHub Actions pipeline. "
    f"Weekends and holidays carry the last market rate. Source: {source}. "
    f"Loaded {loaded_at:%d %b %Y %H:%M} UK time (refreshes daily at {REFRESH_HOUR:02d}:00)."
)
