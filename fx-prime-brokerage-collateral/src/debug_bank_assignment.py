import pandas as pd
from pathlib import Path
from generate_limits import build_limit_schedule
from generate_fx_portfolio import START_DATE, BANK_IDS, TRADE_TYPES, CURRENCY_PAIRS
import numpy as np
from datetime import date
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay, DateOffset

# Reproduce booking logic and inspect the trade on 2026-08-04
business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
business_days = pd.date_range(start=START_DATE, end=date.today() - pd.Timedelta(days=1), freq=business_day)
limit_schedule = build_limit_schedule(end_date=(date.today() - pd.Timedelta(days=1)).isoformat(), seed=42)

rng = np.random.default_rng(42)
trades = []
trade_id = 1
for trade_week in business_days.to_series().groupby(business_days.to_series().dt.to_period('W')).apply(list):
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
            trade_size_usd = float(round(rng.uniform(10_000_000, 20_000_000), 2))
        if trade_type == 'spot':
            value_date = trade_date + DateOffset(days=1)
            value_date = business_days[business_days.get_indexer([value_date], method='bfill')[0]]
            legs = [{'value_date': value_date, 'leg_id': 1, 'leg_amount_usd': trade_size_usd}]
        elif trade_type == 'forward':
            months = int(rng.integers(1, 7))
            value_date = trade_date + DateOffset(months=months)
            value_date = business_days[business_days.get_indexer([value_date], method='bfill')[0]]
            legs = [{'value_date': value_date, 'leg_id': 1, 'leg_amount_usd': trade_size_usd}]
        else:
            near_date = trade_date + DateOffset(days=2)
            near_date = business_days[business_days.get_indexer([near_date], method='bfill')[0]]
            far_months = int(rng.integers(1, 7))
            far_date = trade_date + DateOffset(months=far_months)
            far_date = business_days[business_days.get_indexer([far_date], method='bfill')[0]]
            near_leg = float(round(trade_size_usd * rng.uniform(0.85, 1.0), 2))
            far_leg = float(round(trade_size_usd * rng.uniform(1.0, 1.15), 2))
            legs = [
                {'value_date': near_date, 'leg_id': 1, 'leg_amount_usd': near_leg},
                {'value_date': far_date, 'leg_id': 2, 'leg_amount_usd': far_leg},
            ]
        active_exposure_by_bank = {bank: 0.0 for bank in BANK_IDS}
        for existing in trades:
            if existing['trade_date'] > trade_date:
                continue
            for existing_leg in existing['legs']:
                if trade_date <= existing_leg['value_date']:
                    active_exposure_by_bank[existing['bank_id']] += existing_leg['leg_amount_usd']
        total_trade_exposure = sum(leg['leg_amount_usd'] for leg in legs)
        current_limits = limit_schedule[trade_date.date().isoformat()]
        remaining_capacity = {
            bank: max(current_limits[bank] - active_exposure_by_bank[bank], 0)
            for bank in BANK_IDS
        }
        valid_banks = [
            bank for bank in BANK_IDS
            if remaining_capacity[bank] >= total_trade_exposure * 1.1
        ]
        if trade_date.date().isoformat() == '2026-08-04':
            print('trade_date', trade_date.date())
            print('trade_type', trade_type)
            print('trade_size_usd', trade_size_usd)
            print('legs', legs)
            print('current_limits', current_limits)
            print('active_exposure_by_bank', active_exposure_by_bank)
            print('remaining_capacity', remaining_capacity)
            print('valid_banks', valid_banks)
            print('total_trade_exposure', total_trade_exposure)
            print('required (110%)', total_trade_exposure * 1.1)
        if not valid_banks:
            fallback_banks = [bank for bank in BANK_IDS if remaining_capacity[bank] > 0]
            if trade_date.date().isoformat() == '2026-08-04':
                print('fallback_banks', fallback_banks)
        if not valid_banks:
            valid_banks = fallback_banks
        if not valid_banks:
            bank_id = rng.choice(BANK_IDS)
        else:
            weights = np.array([remaining_capacity[bank] for bank in valid_banks], dtype=float)
            prob = weights / weights.sum()
            bank_id = rng.choice(valid_banks, p=prob)
        if trade_date.date().isoformat() == '2026-08-04':
            print('selected bank', bank_id)
        trades.append({
            'trade_id': f'T{trade_id:05d}',
            'trade_date': trade_date,
            'bank_id': bank_id,
            'type': trade_type,
            'currency_pair': currency_pair,
            'trade_size_usd': trade_size_usd,
            'legs': legs,
        })
        trade_id += 1
