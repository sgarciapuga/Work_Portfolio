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
CURRENCIES = ["GBP", "EUR", "USD"]
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


PERIOD_PRESETS = ["1M", "3M", "YTD", "1Y", "All"]


def preset_start(preset, first_day, last_day):
    """First day of a quick period that ends on last_day, never before the data starts."""
    last = pd.Timestamp(last_day)
    starts = {
        "1M": last - pd.DateOffset(months=1),
        "3M": last - pd.DateOffset(months=3),
        "YTD": pd.Timestamp(last.year, 1, 1),
        "1Y": last - pd.DateOffset(years=1),
        "All": pd.Timestamp(first_day),
    }
    return max(starts[preset].date(), first_day)


def filter_period(pairs, start, end):
    """Rows between start and end, both included."""
    return pairs.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def period_summary(pairs):
    """One row per pair: latest, high, low (and the dates they happened), average,
    change vs previous day and since start.

    A high or low that carries over a weekend is dated on its market day (the first one).
    """
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
            "high_date": series.idxmax(),
            "low": series.min(),
            "low_date": series.idxmin(),
            "average": series.mean(),
            "vs_previous_day": market_days[pair].iloc[-1] / previous - 1,
            "since_start": series.iloc[-1] / series.iloc[0] - 1,
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def priced_in(pairs, base):
    """The other two currencies priced in ``base``, one column per pair.

    For base GBP this returns EUR/GBP and USD/GBP (GBP per EUR and per USD).
    """
    usd_value = {
        "USD": pd.Series(1.0, index=pairs.index),
        "GBP": pairs["GBP/USD"],
        "EUR": pairs["EUR/USD"],
    }
    return pd.DataFrame(
        {f"{cur}/{base}": usd_value[cur] / usd_value[base] for cur in CURRENCIES if cur != base}
    )


def period_csv(pairs):
    """The period's rates as CSV: one row per day, the three pairs and the rate type."""
    out = pairs[PAIRS].round(6)
    out.insert(0, "date", pairs.index.strftime("%Y-%m-%d"))
    out["rate_type"] = pairs["is_raw"].map({True: "market", False: "filled"})
    return out.to_csv(index=False)


def rebased(pairs, columns=("GBP/USD", "EUR/USD")):
    """Pairs indexed to 100 on the first day of the period."""
    selected = pairs[list(columns)]
    return selected / selected.iloc[0] * 100


def moving_average(series, days=MOVING_AVERAGE_DAYS):
    """Trailing average over the last ``days`` days of the period (shorter at the start)."""
    return series.rolling(days, min_periods=1).mean()
