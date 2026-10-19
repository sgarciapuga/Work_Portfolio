"""Run the treasury simulator's daily engine.

Run from the repository root:

    python treasury-simulator/run_daily.py                  # rebuild history, write CSVs only
    python treasury-simulator/run_daily.py --fetch-rates    # also download the latest overnight rates
    python treasury-simulator/run_daily.py --db             # also store the last 14 days in Neon
    python treasury-simulator/run_daily.py --db --full      # store the whole history in Neon

The engine always rebuilds the history from 1 Jan 2025 (it is quick and
deterministic). On Mondays, and with --full, the whole history is stored.
FX rates come from the Daily FX Rates CSV (updated daily by its own workflow).
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / "src"))

from tsim import config  # noqa: E402
from tsim.engine import fx_daily, run_engine  # noqa: E402
from tsim.rates import daily_rates, fetch_all  # noqa: E402
from tsim.static_data import load_static, validate  # noqa: E402

DATA = PROJECT / "data"
RATES_CSV = DATA / "ir_rates.csv"
FX_CSV = PROJECT.parent / "daily-fx-rates" / "data" / "fx_rates.csv"
DAILY_WINDOW_DAYS = 14
FULL_WEEKDAY = 0  # Monday


def update_rates(end, full):
    """Download overnight rates and merge them into data/ir_rates.csv."""
    old = pd.read_csv(RATES_CSV, parse_dates=["rate_date"]) if RATES_CSV.exists() else pd.DataFrame()
    start = config.HISTORY_START - timedelta(days=10)
    if not full and not old.empty:
        start = max(start, end - timedelta(days=30))
    new = fetch_all(start, end)
    if not old.empty:
        old["rate_date"] = old["rate_date"].dt.date
        new = pd.concat([old, new]).drop_duplicates(["rate_date", "currency", "tenor"], keep="last")
    new = new.sort_values(["currency", "rate_date"]).reset_index(drop=True)
    DATA.mkdir(exist_ok=True)
    new.to_csv(RATES_CSV, index=False)
    print(f"Overnight rates: {len(new)} rows, latest {new['rate_date'].max()}")
    return new


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--end", type=date.fromisoformat, help="last day to simulate (default: yesterday)")
    parser.add_argument("--fetch-rates", action="store_true", help="download the latest overnight rates")
    parser.add_argument("--db", action="store_true", help="store the results in Neon")
    parser.add_argument("--full", action="store_true", help="store the whole history (not only the last days)")
    args = parser.parse_args()

    end = args.end or date.today() - timedelta(days=1)
    full = args.full or date.today().weekday() == FULL_WEEKDAY

    static = load_static()
    problems = validate(static)
    if problems:
        raise SystemExit("Static data problems:\n- " + "\n- ".join(problems))

    rates = update_rates(end, full) if args.fetch_rates else None
    if rates is None:
        if not RATES_CSV.exists():
            raise SystemExit(f"No {RATES_CSV.name}: run once with --fetch-rates")
        rates = pd.read_csv(RATES_CSV, parse_dates=["rate_date"])
        rates["rate_date"] = rates["rate_date"].dt.date

    fx = fx_daily(pd.read_csv(FX_CSV), config.HISTORY_START, end)
    on = daily_rates(rates, config.HISTORY_START, end)
    results = run_engine(static, on, fx, config.HISTORY_START, end)

    DATA.mkdir(exist_ok=True)
    for name, df in results.items():
        if name != "opening":
            df.to_csv(DATA / f"{name}.csv", index=False)
    nav = results["nav_daily"]
    last = nav[nav["nav_date"] == end]
    print(f"Simulated {config.HISTORY_START} to {end}: {len(results['cash_txn'])} transactions, "
          f"{len(results['alerts'])} alerts. TRS NAV on {end}: USD {last['nav_usd'].sum():,.0f}")

    if args.db:
        from tsim.db import get_engine, save_engine_results

        from_date = None if full else end - timedelta(days=DAILY_WINDOW_DAYS)
        counts = save_engine_results(get_engine(), results, rates=rates, from_date=from_date)
        print("Stored in Neon:", "whole history" if full else f"from {from_date}", counts)


if __name__ == "__main__":
    main()
