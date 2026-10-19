"""Turn the fee and cost schedules into dated cash flows.

Each schedule row becomes one flow per due date. Dates follow the day rule and
move to a business day of the flow's currency (modified following). Amounts and
timing vary a little (config.FLOW_VARIATION, config.LATE_PAYMENT) with a random
seed taken from the schedule id and the due date, so the same flow always gets
the same result, whatever the run window.
"""

import zlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

from tsim import config
from tsim.calendars import add_business_days, last_business_day, modified_following, nth_business_day

FLOW_COLUMNS = ["value_date", "due_date", "schedule_id", "entity_code", "flow_code", "currency", "amount",
                "counterparty", "counterparty_entity"]


def _months(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _token_date(token, year, month, currency):
    if token == "last_bd":
        return last_business_day(year, month, currency)
    kind, _, n = token.partition(":")
    if kind == "bd":
        return nth_business_day(year, month, int(n), currency)
    if kind == "day":
        day = min(int(n), (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day)
        return modified_following(date(year, month, day), currency)
    raise ValueError(f"Unknown day rule token {token}")


def due_dates(row, start, end):
    """All due dates of one schedule row between start and end (inclusive)."""
    tokens = str(row["day_rule"]).split("|")
    ccy = row["currency"]
    out = []
    if row["frequency"] in ("monthly", "semi_monthly"):
        for y, m in _months(start, end):
            out += [_token_date(t, y, m, ccy) for t in tokens]
    else:  # quarterly / annual: tokens are MM-DD
        for y in range(start.year, end.year + 1):
            for t in tokens:
                mm, dd = (int(x) for x in t.split("-"))
                out.append(modified_following(date(y, mm, dd), ccy))
    return sorted(d for d in out if start <= d <= end)


def _rng(schedule_id, due):
    return np.random.default_rng(zlib.crc32(f"{schedule_id}|{due.isoformat()}".encode()))


def expand_schedule(fee_schedule, start, end, vary=True):
    """Dated flows for every schedule row. Positive amount = received by the entity."""
    rows = []
    for _, r in fee_schedule.iterrows():
        for due in due_dates(r, start - timedelta(days=10), end):
            amount, value = float(r["amount"]), due
            if vary:
                rng = _rng(r["schedule_id"], due)
                spread = config.FLOW_VARIATION.get(r["flow_code"], 0.0)
                if spread:
                    amount *= 1 + float(np.clip(rng.normal(0, spread / 2), -spread, spread))
                late = config.LATE_PAYMENT.get(r["flow_code"])
                if late and rng.random() < late["probability"]:
                    value = add_business_days(due, int(rng.integers(1, late["max_days"] + 1)), r["currency"])
            if start <= value <= end:
                rows.append({
                    "value_date": value, "due_date": due, "schedule_id": r["schedule_id"],
                    "entity_code": r["entity_code"], "flow_code": r["flow_code"], "currency": r["currency"],
                    "amount": round(amount, 2), "counterparty": r["counterparty"],
                    "counterparty_entity": r["counterparty_entity"] if pd.notna(r["counterparty_entity"]) else None,
                })
    return pd.DataFrame(rows, columns=FLOW_COLUMNS).sort_values(["value_date", "schedule_id"]).reset_index(drop=True)
