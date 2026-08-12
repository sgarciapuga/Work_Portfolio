import os
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay


def generate_mark_to_market(n_trades=100, days=30, seed=2026):
    """Create standalone synthetic trade-level MTM and P&L observations."""
    rng = np.random.default_rng(seed)
    trade_ids = [f"T{100000 + i}" for i in range(n_trades)]
    counterparties = [f"CP_{i:03d}" for i in range(1, 1 + max(10, n_trades//10))]
    instruments = ["FX-Swap", "Forward", "Spot", "Option"]
    currencies = ["USD", "EUR", "GBP", "JPY", "CHF"]

    business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    yesterday = pd.date_range(end=date.today(), periods=2, freq=business_day)[-2].date()
    dates = pd.date_range(end=yesterday, periods=days, freq=business_day).date

    rows = []
    for tid in trade_ids:
        cp = rng.choice(counterparties)
        inst = rng.choice(instruments)
        cur = rng.choice(currencies)
        notional = float(round(rng.uniform(1e4, 5e6), 2))
        # Simulate a time series of MTM values for the trade
        base = rng.normal(0, 1)
        drift = rng.normal(0, 0.01)
        volatility = abs(rng.normal(0.02, 0.01))
        mtm_series = base + np.cumsum(rng.normal(drift, volatility, size=len(dates)))
        for d, mtm in zip(dates, mtm_series):
            pnl = mtm * notional * 1e-4
            rows.append({
                "valuation_date": d.isoformat(),
                "trade_id": tid,
                "counterparty": cp,
                "instrument": inst,
                "currency": cur,
                "notional": notional,
                "mtm": float(round(mtm, 6)),
                "pnl": float(round(pnl, 2)),
            })

    df = pd.DataFrame(rows)
    # Sort for readability
    df = df.sort_values(["valuation_date", "trade_id"]).reset_index(drop=True)
    return df


def main(out_path=None):
    """Generate standalone MTM data and write it to ``mark_to_market.csv``."""
    out_dir = out_path or os.path.join(os.path.dirname(__file__), "..", "data", "Mark-to-market")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    df = generate_mark_to_market()
    out_file = os.path.join(out_dir, "mark_to_market.csv")
    df.to_csv(out_file, index=False)
    print(f"Wrote {len(df)} rows to {out_file}")


if __name__ == "__main__":
    main()
