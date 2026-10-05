import os
import zlib
from datetime import date
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

START_DATE = "2026-01-01"


def get_business_days(start_date, end_date):
    """Return US Federal holiday-aware business dates between two endpoints."""
    business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return pd.date_range(start=start_date, end=end_date, freq=business_day)


def generate_mtm_for_portfolio(portfolio_df=None, end_date=None, seed=2026):
    """Simulate daily MTM and P&L for each active generated portfolio trade."""
    if portfolio_df is None:
        path = os.path.join(os.path.dirname(__file__), "..", "data", "FX-portfolio", "portfolio.csv")
        if not os.path.exists(path):
            raise FileNotFoundError("portfolio.csv not found; run generate_fx_datasets first")
        portfolio_df = pd.read_csv(path)

    if end_date is None:
        # use previous business day
        business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
        previous = pd.date_range(end=date.today(), periods=2, freq=business_day)
        end_date = previous[-2].date().isoformat()

    # work with business days up to previous business day
    business_days = get_business_days(START_DATE, end_date)
    last_day = business_days[-1]

    rows = []
    # ensure proper types
    portfolio_df["trade_date"] = pd.to_datetime(portfolio_df["trade_date"])
    portfolio_df["value_date"] = pd.to_datetime(portfolio_df["value_date"])

    # One MTM series per trade and bank, so each bank's slice of a split trade
    # gets its own P&L (they share the trade's price path).
    for (trade_id, bank_id), legs in portfolio_df.groupby(["trade_id", "bank_id"], sort=False):
        trade_date = legs["trade_date"].iloc[0]
        # the trade is live until its last value date; it settles on that date,
        # so (like the portfolio) it carries no MTM on the value date itself
        max_value_date = pd.to_datetime(legs["value_date"].max())
        start = pd.to_datetime(trade_date)
        if start > last_day:
            continue
        # Simulate the trade's full life, then truncate to last_day, so a trade's
        # path doesn't change as the report horizon moves forward.
        life_dates = pd.date_range(start=start, end=max_value_date, freq=CustomBusinessDay(calendar=USFederalHolidayCalendar()))
        life_dates = life_dates[life_dates < max_value_date]
        if len(life_dates) == 0:
            continue

        # simulate mtm series starting at 0, with a per-trade RNG so other trades
        # (added, removed or reordered) can't shift this trade's draws
        rng = np.random.default_rng([seed, zlib.crc32(trade_id.encode())])
        drift = rng.normal(0, 0.0001)
        vol = abs(rng.normal(0.001, 0.0005))
        steps = rng.normal(drift, vol, size=len(life_dates))
        mtm_series = np.cumsum(steps)
        visible = life_dates <= last_day
        dates = life_dates[visible]
        mtm_series = mtm_series[visible]

        # this bank's trade size (first leg row)
        trade_size = float(legs.iloc[0]["trade_size_usd"])

        for d, mtm in zip(dates, mtm_series):
            pnl = float(round(mtm * trade_size, 2))
            rows.append({
                "report_date": d.date().isoformat(),
                "trade_id": trade_id,
                "bank_id": bank_id,
                "mtm": float(round(mtm, 6)),
                "pnl": pnl,
                "trade_size_usd": trade_size,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["report_date", "trade_id"]).reset_index(drop=True)
    return df


def main(out_path=None):
    """Generate portfolio MTM data and write it to its CSV output."""
    df = generate_mtm_for_portfolio()
    out_dir = out_path or os.path.join(os.path.dirname(__file__), "..", "data", "Mark-to-market")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "mark_to_market_portfolio.csv")
    df.to_csv(out_file, index=False)
    print(f"Wrote {len(df)} rows to {out_file}")


if __name__ == "__main__":
    main()
