import os
import warnings
from datetime import date
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay, DateOffset
from generate_limits import BANK_LIMITS, build_limit_schedule

START_DATE = "2026-01-01"
BANK_IDS = ["bank_1", "bank_2", "bank_3", "bank_4", "fx_pb_1"]
CURRENCY_PAIRS = ["EUR/USD", "GBP/USD", "EUR/GBP"]
TRADE_TYPES = ["spot", "forward", "swap"]


def get_business_days(start_date, end_date):
    business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return pd.date_range(start=start_date, end=end_date, freq=business_day)


def ensure_business_day(timestamp, business_days):
    if timestamp in business_days:
        return timestamp
    idx = business_days.get_indexer([timestamp], method="bfill")[0]
    return business_days[idx]


def generate_fx_portfolio(end_date=None, seed=42):
    if end_date is None:
        business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
        previous = pd.date_range(end=date.today(), periods=2, freq=business_day)
        end_date = previous[-2].date().isoformat()

    business_days = get_business_days(START_DATE, end_date)
    rng = np.random.default_rng(seed)

    trades = []
    trade_id = 1
    limit_schedule = build_limit_schedule(end_date=end_date, seed=seed)

    weekly_groups = business_days.to_series().groupby(business_days.to_series().dt.to_period("W")).apply(list)
    for trade_week in weekly_groups:
        sample_dates = rng.choice(trade_week, size=min(5, len(trade_week)), replace=False)
        for trade_date in sorted(sample_dates):
            trade_type = rng.choice(TRADE_TYPES, p=[0.4, 0.35, 0.25])
            currency_pair = rng.choice(CURRENCY_PAIRS)
            size_category = rng.random()
            if size_category < 0.05:
                trade_size_usd = float(round(rng.uniform(50_000, 200_000), 2))
            elif size_category < 0.2:
                trade_size_usd = float(round(rng.uniform(200_000, 1_000_000), 2))
            elif size_category < 0.8:
                trade_size_usd = float(round(rng.uniform(1_000_000, 3_000_000), 2))
            elif size_category < 0.95:
                trade_size_usd = float(round(rng.uniform(3_000_000, 10_000_000), 2))
            else:
                # Cap the largest trades at 10m to keep portfolio realism aligned with average trade size ~2m
                trade_size_usd = float(round(rng.uniform(3_000_000, 10_000_000), 2))

            if trade_type == "spot":
                value_date = ensure_business_day(trade_date + DateOffset(days=1), business_days)
                legs = [{"value_date": value_date, "leg_id": 1, "leg_amount_usd": trade_size_usd}]
            elif trade_type == "forward":
                months = int(rng.integers(1, 7))
                value_date = ensure_business_day(trade_date + DateOffset(months=months), business_days)
                legs = [{"value_date": value_date, "leg_id": 1, "leg_amount_usd": trade_size_usd}]
            else:  # swap
                near_date = ensure_business_day(trade_date + DateOffset(days=2), business_days)
                far_months = int(rng.integers(1, 7))
                far_date = ensure_business_day(trade_date + DateOffset(months=far_months), business_days)
                near_leg = float(round(trade_size_usd * rng.uniform(0.85, 1.0), 2))
                far_leg = float(round(trade_size_usd * rng.uniform(1.0, 1.15), 2))
                legs = [
                    {"value_date": near_date, "leg_id": 1, "leg_amount_usd": near_leg},
                    {"value_date": far_date, "leg_id": 2, "leg_amount_usd": far_leg},
                ]

            active_exposure_by_bank = {bank: 0.0 for bank in BANK_IDS}
            for existing in trades:
                if existing["trade_date"] > trade_date:
                    continue
                for existing_leg in existing["legs"]:
                    if trade_date <= existing_leg["value_date"]:
                        active_exposure_by_bank[existing["bank_id"]] += existing_leg["leg_amount_usd"]

            total_trade_exposure = sum(leg["leg_amount_usd"] for leg in legs)
            current_limits = limit_schedule[trade_date.date().isoformat()]
            remaining_capacity = {
                bank: max(current_limits[bank] - active_exposure_by_bank[bank], 0)
                for bank in BANK_IDS
            }
            valid_banks = [
                bank for bank in BANK_IDS
                if remaining_capacity[bank] >= total_trade_exposure * 1.1
            ]
            if not valid_banks:
                valid_banks = [bank for bank in BANK_IDS if remaining_capacity[bank] >= total_trade_exposure]
            if not valid_banks:
                warnings.warn(
                    f"No bank has full capacity for trade {trade_id} of size {total_trade_exposure:.2f}; "
                    "assigning randomly to maintain portfolio continuity.",
                    UserWarning,
                )
                bank_id = rng.choice(BANK_IDS)
            else:
                weights = np.array([remaining_capacity[bank] for bank in valid_banks], dtype=float)
                prob = weights / weights.sum()
                bank_id = rng.choice(valid_banks, p=prob)

            trades.append({
                "trade_id": f"T{trade_id:05d}",
                "trade_date": trade_date,
                "bank_id": bank_id,
                "type": trade_type,
                "currency_pair": currency_pair,
                "trade_size_usd": trade_size_usd,
                "legs": legs,
            })
            trade_id += 1

    rows = []
    for report_date in business_days:
        for trade in trades:
            if trade["trade_date"] > report_date:
                continue
            for leg in trade["legs"]:
                if report_date <= leg["value_date"]:
                    rows.append({
                        "report_date": report_date.date().isoformat(),
                        "bank_id": trade["bank_id"],
                        "trade_id": trade["trade_id"],
                        "type": trade["type"],
                        "trade_date": trade["trade_date"].date().isoformat(),
                        "value_date": leg["value_date"].date().isoformat(),
                        "currency_pair": trade["currency_pair"],
                        "trade_size_usd": leg["leg_amount_usd"],
                        "leg_id": leg["leg_id"],
                    })

    df = pd.DataFrame(rows)
    df = df[["report_date", "bank_id", "trade_id", "type", "trade_date", "value_date", "currency_pair", "trade_size_usd", "leg_id"]]
    return df


def main(out_path=None):
    out_dir = out_path or os.path.join(os.path.dirname(__file__), "..", "data", "FX-portfolio")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    df = generate_fx_portfolio()
    out_file = os.path.join(out_dir, "portfolio.csv")
    df.to_csv(out_file, index=False)
    print(f"Wrote {len(df)} rows to {out_file}")


if __name__ == "__main__":
    main()
