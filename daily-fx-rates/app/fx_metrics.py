"""Calculations behind the FX rates Streamlit report.

Rates are stored as units of currency per 1 USD (``fx_to_usd``). The report
shows them as market pairs: GBP/USD and EUR/USD (USD per unit), and GBP/EUR
(EUR per GBP), which is calculated from both.

The definitions match the Google Data Studio report:
- "vs previous day" compares the last two market days, so a weekend or holiday
  (a ``filled`` rate) still shows the latest market move.
- High, low and average use every calendar day in the period.
- "since" compares the last day with the first day of the period.
"""

import pandas as pd

QUALITY_RAW = "raw"
PAIRS = ["GBP/USD", "EUR/USD", "GBP/EUR"]
MOVING_AVERAGE_DAYS = 30


def to_pairs(rates):
    """Turn fx_rates rows (date, currency, fx_to_usd, fx_quality_flag) into one row per date.

    Returns a frame indexed by date with one column per pair and ``is_raw``,
    which is True when both EUR and GBP came from the source that day.
    """
    df = rates.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]
    if "fx_quality_flag" not in df.columns:
        df["fx_quality_flag"] = QUALITY_RAW

    df["date"] = pd.to_datetime(df["date"])
    df["currency"] = df["currency"].astype(str).str.upper().str.strip()
    df = df[df["currency"].isin(["EUR", "GBP"])]
    df = df.drop_duplicates(subset=["date", "currency"], keep="last")

    wide = df.pivot(index="date", columns="currency", values="fx_to_usd").sort_index()
    wide = wide.dropna(subset=["EUR", "GBP"])
    flags = df.pivot(index="date", columns="currency", values="fx_quality_flag").reindex(wide.index)

    pairs = pd.DataFrame(
        {
            "GBP/USD": 1 / wide["GBP"],
            "EUR/USD": 1 / wide["EUR"],
            "GBP/EUR": wide["EUR"] / wide["GBP"],
        }
    )
    pairs["is_raw"] = (flags["EUR"] == QUALITY_RAW) & (flags["GBP"] == QUALITY_RAW)
    return pairs


def filter_period(pairs, start, end):
    """Rows between start and end, both included."""
    return pairs.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def period_summary(pairs):
    """One row per pair: latest, high, low, average, change vs previous day and since start."""
    market_days = pairs[pairs["is_raw"]]
    if len(market_days) < 2:
        market_days = pairs

    rows = {}
    for pair in PAIRS:
        series = pairs[pair]
        previous = market_days[pair].iloc[-2] if len(market_days) >= 2 else float("nan")
        rows[pair] = {
            "latest": series.iloc[-1],
            "high": series.max(),
            "low": series.min(),
            "average": series.mean(),
            "vs_previous_day": market_days[pair].iloc[-1] / previous - 1,
            "since_start": series.iloc[-1] / series.iloc[0] - 1,
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def rebased(pairs, columns=("GBP/USD", "EUR/USD")):
    """Pairs indexed to 100 on the first day of the period."""
    selected = pairs[list(columns)]
    return selected / selected.iloc[0] * 100


def moving_average(series, days=MOVING_AVERAGE_DAYS):
    """Trailing average over the last ``days`` days of the period (shorter at the start)."""
    return series.rolling(days, min_periods=1).mean()
