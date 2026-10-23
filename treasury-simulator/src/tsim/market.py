"""Market data helpers: FX in market convention and implied FX forwards.

fx_rates stores units of each currency per 1 USD. Dealers quote:
  EUR/USD and GBP/USD = USD per 1 EUR / GBP   (1 / fx_to_usd)
  USD/CHF             = CHF per 1 USD          (fx_to_usd)

Implied forward (covered interest parity, simple interest):
  F = S x (1 + r_quote x days / basis_quote) / (1 + r_base x days / basis_base)
Forward points are quoted in pips: (F - S) x 10,000.
Here the overnight rate stands in for the 1M / 3M term rate: a simplification,
fine for a picture of the mechanics (Tier 3), not for pricing.
"""

import pandas as pd

from tsim import config

PAIRS = {  # pair -> (base ccy, quote ccy)
    "EUR/USD": ("EUR", "USD"),
    "GBP/USD": ("GBP", "USD"),
    "USD/CHF": ("USD", "CHF"),
}
TENORS = {"1M": 30, "3M": 91}
PIP = 10_000


def market_quotes(fx_rows):
    """One row per date with EUR/USD, GBP/USD, USD/CHF and is_raw (all three from the market that day)."""
    df = fx_rows.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["currency"] = df["currency"].astype(str).str.upper()
    df = df[df["currency"].isin(["EUR", "GBP", "CHF"])].drop_duplicates(["date", "currency"], keep="last")
    wide = df.pivot(index="date", columns="currency", values="fx_to_usd").sort_index().dropna()
    flags = df.pivot(index="date", columns="currency", values="fx_quality_flag").reindex(wide.index)
    out = pd.DataFrame({"EUR/USD": 1 / wide["EUR"], "GBP/USD": 1 / wide["GBP"], "USD/CHF": wide["CHF"]})
    out["is_raw"] = (flags == "raw").all(axis=1) if "fx_quality_flag" in fx_rows.columns else True
    return out


def forward_rate(spot, r_base, r_quote, days, basis_base, basis_quote):
    return spot * (1 + r_quote * days / basis_quote) / (1 + r_base * days / basis_base)


def implied_forwards(quotes, on_rates, day):
    """Spot, 1M and 3M forward and forward points (pips) per pair on one day."""
    spot_row, rates = quotes.loc[day], on_rates.loc[day]
    rows = []
    for pair, (base, quote) in PAIRS.items():
        spot = spot_row[pair]
        row = {"pair": pair, "spot": spot, "rate_base": rates[base], "rate_quote": rates[quote]}
        for tenor, days in TENORS.items():
            fwd = forward_rate(spot, rates[base], rates[quote], days,
                               config.DAY_COUNT_BASIS[base], config.DAY_COUNT_BASIS[quote])
            row[f"fwd_{tenor}"] = fwd
            row[f"points_{tenor}"] = (fwd - spot) * PIP
        rows.append(row)
    return pd.DataFrame(rows)


def forward_points_history(quotes, on_rates, tenor="3M"):
    """Forward points (pips) per pair for every day both spot and rates exist."""
    days = TENORS[tenor]
    common = quotes.index.intersection(on_rates.index)
    out = pd.DataFrame(index=common)
    for pair, (base, quote) in PAIRS.items():
        s, rb, rq = quotes.loc[common, pair], on_rates.loc[common, base], on_rates.loc[common, quote]
        fwd = forward_rate(s, rb, rq, days, config.DAY_COUNT_BASIS[base], config.DAY_COUNT_BASIS[quote])
        out[pair] = (fwd - s) * PIP
    return out


# ---------------- FX deals (Phase 3) ----------------
def forward_fx_to_usd(fx_to_usd, on_ccy, on_usd, ccy, days):
    """Units of ccy per 1 USD for a value date `days` ahead (covered interest parity, simple interest)."""
    if ccy == "USD":
        return 1.0
    return forward_rate(fx_to_usd, on_usd, on_ccy, days, config.DAY_COUNT_BASIS["USD"], config.DAY_COUNT_BASIS[ccy])


def pair_of(ccy1, ccy2):
    """(base, quote) in market order, e.g. ('GBP', 'USD') or ('USD', 'CHF')."""
    order = config.FX_PAIR_PRIORITY
    return (ccy1, ccy2) if order.index(ccy1) < order.index(ccy2) else (ccy2, ccy1)


def deal_rate(buy_ccy, buy_amount, sell_ccy, sell_amount):
    """The deal's rate in market convention: units of the quote currency per 1 base."""
    base, _ = pair_of(buy_ccy, sell_ccy)
    return sell_amount / buy_amount if base == buy_ccy else buy_amount / sell_amount


def differentials_bp(on_rates):
    """EUR, GBP and CHF overnight rate minus SOFR, in basis points."""
    return pd.DataFrame({c: (on_rates[c] - on_rates["USD"]) * 10_000 for c in ["EUR", "GBP", "CHF"]},
                        index=on_rates.index)
