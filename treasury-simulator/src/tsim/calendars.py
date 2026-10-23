"""Business days per currency.

A payment in a currency can only settle on a business day of that currency:
USD = US federal (Fed) holidays, EUR = TARGET (ECB), GBP = England, CHF = Zurich.
"""

from datetime import date, timedelta
from functools import lru_cache

import holidays


@lru_cache(maxsize=None)
def _holidays(currency, year):
    if currency == "USD":
        h = holidays.country_holidays("US", years=year)
    elif currency == "EUR":
        h = holidays.financial_holidays("ECB", years=year)
    elif currency == "GBP":
        h = holidays.country_holidays("GB", subdiv="ENG", years=year)
    elif currency == "CHF":
        h = holidays.country_holidays("CH", subdiv="ZH", years=year)
    else:
        raise ValueError(f"No calendar for {currency}")
    return frozenset(h.keys())


def is_business_day(d, currency):
    return d.weekday() < 5 and d not in _holidays(currency, d.year)


def next_business_day(d, currency):
    """d itself if it is a business day, otherwise the next one."""
    while not is_business_day(d, currency):
        d += timedelta(days=1)
    return d


def previous_business_day(d, currency):
    while not is_business_day(d, currency):
        d -= timedelta(days=1)
    return d


def modified_following(d, currency):
    """Next business day, unless that is in the next month: then the previous one."""
    nxt = next_business_day(d, currency)
    return nxt if nxt.month == d.month else previous_business_day(d, currency)


def add_business_days(d, n, currency):
    d = next_business_day(d, currency)
    for _ in range(n):
        d = next_business_day(d + timedelta(days=1), currency)
    return d


def nth_business_day(year, month, n, currency):
    """n-th business day of the month (n=1 is the first)."""
    return add_business_days(date(year, month, 1), n - 1, currency)


def last_business_day(year, month, currency):
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return previous_business_day(nxt - timedelta(days=1), currency)


def is_joint_business_day(d, currencies):
    """A business day in every currency (an FX deal between them can settle)."""
    return all(is_business_day(d, c) for c in currencies)


def add_joint_business_days(d, n, currencies):
    while not is_joint_business_day(d, currencies):
        d += timedelta(days=1)
    for _ in range(n):
        d += timedelta(days=1)
        while not is_joint_business_day(d, currencies):
            d += timedelta(days=1)
    return d


def last_joint_business_day(year, month, currencies):
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    while not is_joint_business_day(d, currencies):
        d -= timedelta(days=1)
    return d


def add_months(d, months, currencies):
    """Same day n months later (end of month if shorter), then modified following on the joint calendar."""
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    target = date(y, m, min(d.day, last))
    nxt = add_joint_business_days(target, 0, currencies)
    if nxt.month == target.month:
        return nxt
    while not is_joint_business_day(target, currencies):
        target -= timedelta(days=1)
    return target


def business_days(start, end, currency):
    d, out = start, []
    while d <= end:
        if is_business_day(d, currency):
            out.append(d)
        d += timedelta(days=1)
    return out
