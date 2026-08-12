import os
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

    rng = np.random.default_rng(seed)

    rows = []
    # ensure proper types
    portfolio_df["trade_date"] = pd.to_datetime(portfolio_df["trade_date"])
    portfolio_df["value_date"] = pd.to_datetime(portfolio_df["value_date"])

    trades = portfolio_df.drop_duplicates(subset=["trade_id"]).set_index("trade_id")

    for trade_id, t in trades.iterrows():
        trade_date = t["trade_date"].to_pydatetime().date()
        # active range: from trade_date to min(value_date - 1, last_day)
        legs = portfolio_df[portfolio_df["trade_id"] == trade_id]
        # use earliest value_date among legs as final settle for MTM of trade (per leg MTM could differ, but simplified)
        max_value_date = pd.to_datetime(legs["value_date"].max())
        start = pd.to_datetime(trade_date)
        end = min(max_value_date, last_day)
        if start > end:
            continue
        dates = pd.date_range(start=start, end=end, freq=CustomBusinessDay(calendar=USFederalHolidayCalendar()))
        if len(dates) == 0:
            continue

        # simulate mtm series starting at 0
        drift = rng.normal(0, 0.0001)
        vol = abs(rng.normal(0.001, 0.0005))
        steps = rng.normal(drift, vol, size=len(dates))
        mtm_series = np.cumsum(steps)

        # find trade_size_usd per trade (use first row's trade_size_usd)
        trade_size = float(legs.iloc[0]["trade_size_usd"])
        bank_id = legs.iloc[0]["bank_id"]

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
