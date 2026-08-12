import os
from datetime import date
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay


START_DATE = "2026-01-01"
BANK_LIMITS = {
    "bank_1": 20_000_000,
    "bank_2": 35_000_000,
    "bank_3": 25_000_000,
    "bank_4": 30_000_000,
    "fx_pb_1": 50_000_000,
}


def get_business_days(start_date, end_date):
    """Return US Federal holiday-aware business dates between two endpoints."""
    business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return pd.date_range(start=start_date, end=end_date, freq=business_day)


def round_limit(value):
    """Round a credit limit to the project's 250,000 USD increment."""
    return float(round(value / 250_000) * 250_000)


def build_limit_schedule(end_date=None, seed=42):
    """Create a dated credit-limit schedule with semiannual reviews."""
    if end_date is None:
        business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
        previous = pd.date_range(end=date.today(), periods=2, freq=business_day)
        end_date = previous[-2].date().isoformat()

    business_days = get_business_days(START_DATE, end_date)
    review_dates = pd.date_range(start=START_DATE, end=end_date, freq="6MS")
    review_dates = [d if d in business_days else business_days[business_days.get_indexer([d], method="bfill")[0]] for d in review_dates]

    rng = np.random.default_rng(seed)
    current_limits = BANK_LIMITS.copy()
    schedule = {}

    def adjust_limits(limits):
        banks = list(limits.keys())
        values = []
        for bank_id in banks:
            change = rng.uniform(1_000_000, 3_000_000)
            sign = rng.choice([-1, 1])
            updated = limits[bank_id] + sign * change
            updated = max(updated, 5_000_000)
            values.append(round_limit(updated))

        total = sum(values)
        remainder = 160_000_000 - total
        step = 250_000
        while remainder != 0:
            idx = rng.integers(len(values))
            adjustment = step if remainder > 0 else -step
            candidate = values[idx] + adjustment
            if candidate >= 5_000_000:
                values[idx] = candidate
                remainder -= adjustment

        return dict(zip(banks, values))

    for current_date in business_days:
        if current_date in review_dates and current_date != pd.Timestamp(START_DATE):
            current_limits = adjust_limits(current_limits)
        schedule[current_date.date().isoformat()] = current_limits.copy()

    return schedule


def exposures_from_portfolio(portfolio_df):
    """Aggregate portfolio trade size by reporting date and bank."""
    if portfolio_df is None or portfolio_df.empty:
        return {}

    df = portfolio_df[["report_date", "bank_id", "trade_size_usd"]]
    grouped = df.groupby(["report_date", "bank_id"], as_index=False)["trade_size_usd"].sum()
    return {
        (row["report_date"], row["bank_id"]): float(row["trade_size_usd"])
        for _, row in grouped.iterrows()
    }


def generate_limits(end_date=None, portfolio_df=None, seed=42):
    """Return daily bank limits, exposure, and remaining capacity as a DataFrame."""
    if end_date is None:
        business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
        previous = pd.date_range(end=date.today(), periods=2, freq=business_day)
        end_date = previous[-2].date().isoformat()

    business_days = get_business_days(START_DATE, end_date)
    review_dates = pd.date_range(start=START_DATE, end=end_date, freq="6MS")
    review_dates = [d if d in business_days else business_days[business_days.get_indexer([d], method="bfill")[0]] for d in review_dates]

    rng = np.random.default_rng(seed)
    current_limits = BANK_LIMITS.copy()
    exposures = exposures_from_portfolio(portfolio_df)
    rows = []

    def round_limit(value):
        return float(round(value / 250_000) * 250_000)

    def adjust_limits(limits):
        banks = list(limits.keys())
        values = []
        for bank_id in banks:
            change = rng.uniform(1_000_000, 3_000_000)
            sign = rng.choice([-1, 1])
            updated = limits[bank_id] + sign * change
            updated = max(updated, 5_000_000)
            values.append(round_limit(updated))

        total = sum(values)
        remainder = 160_000_000 - total
        step = 250_000
        while remainder != 0:
            idx = rng.integers(len(values))
            adjustment = step if remainder > 0 else -step
            candidate = values[idx] + adjustment
            if candidate >= 5_000_000:
                values[idx] = candidate
                remainder -= adjustment

        return dict(zip(banks, values))

    for current_date in business_days:
        if current_date in review_dates and current_date != pd.Timestamp(START_DATE):
            current_limits = adjust_limits(current_limits)

        report_date = current_date.date().isoformat()
        for bank_id, limit_amount in current_limits.items():
            exposure = exposures.get((report_date, bank_id), 0.0)
            available = float(round(limit_amount - exposure, 2))

            rows.append({
                "as_of_date": current_date.date().isoformat(),
                "bank_id": bank_id,
                "credit_limit_usd": limit_amount,
                "counterparty_exposure_usd": exposure,
                "limit_available_usd": available,
            })

    df = pd.DataFrame(rows)
    df = df[["as_of_date", "bank_id", "credit_limit_usd", "counterparty_exposure_usd", "limit_available_usd"]]
    return df


def main(out_path=None):
    """Generate the limits table and write it to ``limits.csv``."""
    out_dir = out_path or os.path.join(os.path.dirname(__file__), "..", "data", "Limits")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    df = generate_limits()
    out_file = os.path.join(out_dir, "limits.csv")
    df.to_csv(out_file, index=False)
    print(f"Wrote {len(df)} rows to {out_file}")


if __name__ == "__main__":
    main()
