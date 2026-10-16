"""Written summary ("In brief") of the selected period for the Overview page.

Built from the same figures as the KPI cards and charts, so it updates with the
daily data and the period picker. The wording is rule-based. ``fmt`` decides how
a change is shown: plain text by default, coloured pills in the app.
"""

import pandas as pd

from fx_metrics import moving_average

FLAT = 0.001  # a change under 0.1% reads as "level" / "held steady"
NEAR = 0.1  # in the top or bottom 10% of the period's range reads as "close to" the high or low


def plain_change(change):
    return f"{change:+.2%}"


def _day(ts, weekday=False):
    ts = pd.Timestamp(ts)
    return (f"{ts:%a} " if weekday else "") + f"{ts.day} {ts:%b}"


def _verb(change):
    if abs(change) < FLAT:
        return "held steady at"
    return "rose" if change > 0 else "fell"


def headline(summary, start):
    change = summary.loc["GBP/EUR", "since_start"]
    if abs(change) < FLAT:
        return f"The pound and the euro are level since {_day(start)}"
    winner, loser = ("pound", "euro") if change > 0 else ("euro", "pound")
    return f"The {winner} has gained on the {loser} since {_day(start)}"


def against_dollar(summary, fmt=plain_change):
    gbp, eur = summary.loc["GBP/USD", "since_start"], summary.loc["EUR/USD", "since_start"]
    if gbp <= -FLAT and eur <= -FLAT:
        return f"Both lost ground against the dollar: the pound {fmt(gbp)} and the euro {fmt(eur)}."
    if gbp >= FLAT and eur >= FLAT:
        return f"Both gained against the dollar: the pound {fmt(gbp)} and the euro {fmt(eur)}."
    return f"Against the dollar, the pound {_verb(gbp)} {fmt(gbp)} while the euro {_verb(eur)} {fmt(eur)}."


def gbp_eur_position(pairs, summary, fmt=plain_change):
    row = summary.loc["GBP/EUR"]
    sentence = f"GBP/EUR is {fmt(row.since_start)} at {row.latest:.4f}, "
    span = row.high - row.low
    position = (row.latest - row.low) / span if span else 0.5  # 0 = at the low, 1 = at the high
    if position >= 1 - NEAR:
        sentence += f"close to its period high of {row.high:.4f} on {_day(row.high_date)}"
    elif position <= NEAR:
        sentence += f"close to its period low of {row.low:.4f} on {_day(row.low_date)}"
    else:
        sentence += (
            f"between its low of {row.low:.4f} ({_day(row.low_date)}) "
            f"and high of {row.high:.4f} ({_day(row.high_date)})"
        )
    average = moving_average(pairs["GBP/EUR"]).iloc[-1]
    if abs(row.latest / average - 1) < FLAT:
        return sentence + ", in line with its 30-day average."
    side = "above" if row.latest > average else "below"
    return sentence + f", and {side} its 30-day average of {average:.4f}."


def last_market_day(pairs, summary, fmt=plain_change):
    market_days = pairs.index[pairs["is_raw"]]
    if len(market_days) < 2 or summary["vs_previous_day"].isna().any():
        return ""
    moves = ", ".join(f"{pair} {fmt(summary.loc[pair, 'vs_previous_day'])}" for pair in summary.index[:-1])
    last = summary.index[-1]
    return (
        f"On {_day(market_days[-1], weekday=True)}, the last market day, "
        f"{moves} and {last} {fmt(summary.loc[last, 'vs_previous_day'])}."
    )


def period_story(pairs, summary, fmt=plain_change):
    """(headline, sentences) for the period in ``pairs``."""
    sentences = [
        against_dollar(summary, fmt),
        gbp_eur_position(pairs, summary, fmt),
        last_market_day(pairs, summary, fmt),
    ]
    return headline(summary, pairs.index[0]), [s for s in sentences if s]
