from datetime import date

import pandas as pd

from tsim.calendars import (add_business_days, is_business_day, last_business_day, modified_following,
                            nth_business_day)
from tsim.schedule import due_dates, expand_schedule
from tsim.static_data import load_static


def test_currency_calendars():
    assert not is_business_day(date(2025, 4, 18), "GBP")        # Good Friday
    assert not is_business_day(date(2025, 4, 21), "EUR")        # Easter Monday (TARGET)
    assert is_business_day(date(2025, 4, 21), "USD")            # not a US holiday
    assert not is_business_day(date(2025, 7, 4), "USD")         # Independence Day
    assert not is_business_day(date(2025, 8, 1), "CHF")         # Swiss National Day
    assert not is_business_day(date(2025, 8, 25), "GBP")        # summer bank holiday
    assert not is_business_day(date(2025, 1, 4), "USD")         # Saturday


def test_rolls():
    assert modified_following(date(2025, 5, 31), "GBP") == date(2025, 5, 30)   # Sat at month end -> back
    assert modified_following(date(2025, 3, 1), "GBP") == date(2025, 3, 3)     # Sat -> Monday
    assert last_business_day(2025, 12, "GBP") == date(2025, 12, 31)
    assert nth_business_day(2025, 1, 2, "GBP") == date(2025, 1, 3)              # 1 Jan holiday
    assert add_business_days(date(2025, 4, 17), 1, "GBP") == date(2025, 4, 22)


def _row(sid, freq, rule, ccy="GBP"):
    return pd.Series({"schedule_id": sid, "frequency": freq, "day_rule": rule, "currency": ccy})


def test_due_dates_by_frequency():
    jan_mar = (date(2025, 1, 1), date(2025, 3, 31))
    assert due_dates(_row("a", "monthly", "day:25"), *jan_mar) == [date(2025, 1, 27), date(2025, 2, 25), date(2025, 3, 25)]  # 25 Jan is a Saturday
    assert len(due_dates(_row("b", "semi_monthly", "day:15|last_bd", "USD"), *jan_mar)) == 6
    q = due_dates(_row("c", "quarterly", "01-10|04-10|07-10|10-10"), date(2025, 1, 1), date(2025, 12, 31))
    assert q == [date(2025, 1, 10), date(2025, 4, 10), date(2025, 7, 10), date(2025, 10, 10)]


def test_expand_schedule_is_reproducible_and_varies_a_little():
    fees = load_static()["fee_schedule"]
    a = expand_schedule(fees, date(2025, 1, 1), date(2025, 6, 30))
    b = expand_schedule(fees, date(2025, 1, 1), date(2025, 6, 30))
    pd.testing.assert_frame_equal(a, b)
    # A shorter window gives the same flows for the shared dates (daily runs match the backfill)
    c = expand_schedule(fees, date(2025, 3, 1), date(2025, 6, 30))
    shared = a[a["value_date"] >= date(2025, 3, 1)].reset_index(drop=True)
    pd.testing.assert_frame_equal(shared, c.reset_index(drop=True))
    payroll = a[a["schedule_id"] == "F05"]["amount"]
    assert ((payroll / -1_600_000 - 1).abs() <= 0.02 + 1e-9).all()
    assert payroll.nunique() > 1                    # amounts do vary
    exact = expand_schedule(fees, date(2025, 1, 1), date(2025, 6, 30), vary=False)
    assert (exact[exact["schedule_id"] == "F05"]["amount"] == -1_600_000).all()


def test_flows_land_on_business_days_and_ic_recharges_net_to_zero():
    flows = expand_schedule(load_static()["fee_schedule"], date(2025, 1, 1), date(2025, 12, 31))
    assert all(is_business_day(d, c) for d, c in zip(flows["value_date"], flows["currency"]))
    ic = flows[flows["counterparty_entity"].notna()]
    assert abs(ic["amount"].sum()) < 0.01
