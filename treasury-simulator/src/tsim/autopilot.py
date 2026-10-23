"""Phase 3 autopilot: the treasurer's daily decisions, written as rules.

The engine does the bookkeeping and the autopilot only decides: each method looks at
the engine's state on day d and returns what to do. The Today page (Phase 3b) will
replace some of these decisions with the user's own. Each decision comes with its reason
in plain English, which the engine writes to the treasurer's log (the activity table).
Settings are in config.py.

Rules
- FX orders: on the last joint business day of the month each service company converts
  its foreign-currency IC balances into its own currency. A few business days ahead it
  books the known amount as an internal forward with TRS; on the day, any remainder is
  converted at spot.
- Cover: TRS nets the internal deals booked today per currency and value date, and
  covers each net amount with one external forward against USD.
- Flatten: a currency still outside the +/- USD 50k tolerance (counting the interest
  that accrues until the next business day) is brought back to zero with an external
  spot deal (T+2).
- IC deposits: on the first business day of the month, and when a deposit matures, cash
  the entity will not need before the deposit matures goes into a 3-month fixed deposit:
  the lowest point of its projected on-call balance over the 3 months, less a floor of
  about one month of scheduled outflows (its OPEX).
- Invest / divest: cash above the operating minimum goes into the MMF (call deposit for
  CHF); a shortfall is redeemed. If the projected cash over the 5-day look-ahead
  (scheduled flows and FX settlements) dips below what the MMF can cover, the shortfall
  is funded from USD with a 1-month swap, on a day both markets are open.
"""

import math
from collections import defaultdict

import pandas as pd

from tsim import config
from tsim.calendars import (add_joint_business_days, add_months, is_business_day, is_joint_business_day,
                            last_joint_business_day, nth_business_day)


class Autopilot:
    def __init__(self, engine):
        self.eng = engine
        ent = engine.static["entities"]
        self.functional = {r.entity_code: r.functional_ccy for r in ent.itertuples() if r.role == "service_company"}
        flows = engine.flows
        self.flows = {key: g[["value_date", "amount"]].reset_index(drop=True)
                      for key, g in flows.groupby(["entity_code", "currency"])}
        self.flows_by_ccy = {ccy: g[["value_date", "amount"]].reset_index(drop=True)
                             for ccy, g in flows.groupby("currency")}
        self.hedged_months = set()

    # ---------------- helpers ----------------
    def _flows(self, ent, ccy, after, until, outflows_only=False):
        """Sum of the entity's scheduled flows in ccy with after < value date <= until."""
        f = self.flows.get((ent, ccy))
        if f is None:
            return 0.0
        amounts = f.loc[(f["value_date"] > after) & (f["value_date"] <= until), "amount"]
        return float(amounts[amounts < 0].sum() if outflows_only else amounts.sum())

    def conversion_date(self, d):
        return last_joint_business_day(d.year, d.month, config.CURRENCIES)

    def working_balance(self, ent, ccy, d):
        """The floor the entity keeps on call: its scheduled outflows over the next month, plus a buffer."""
        until = add_months(d, config.IC_WORKING_BALANCE_MONTHS, [ccy])
        return -self._flows(ent, ccy, d, until, outflows_only=True) * (1 + config.IC_WORKING_BALANCE_BUFFER)

    def available_for_term(self, ent, ccy, d):
        """What can be locked in a term deposit today without the on-call balance dropping below the
        working balance before the deposit matures: the lowest point of the projected balance (today's
        balance plus the scheduled flows) over the tenor, minus the working balance. Flows in other
        currencies count too, at today's rate: the entity converts them into ccy at month end.

        Returns (available, lowest projected balance, working balance).
        """
        until = add_months(d, config.IC_DEPOSIT_TENOR_MONTHS, [ccy])
        fx = self.eng.fx.loc[d]
        upcoming = []
        for c in config.CURRENCIES:
            f = self.flows.get((ent, c))
            if f is not None:
                f = f[(f["value_date"] > d) & (f["value_date"] <= until)]
                upcoming.append(f.assign(amount=f["amount"] * fx[ccy] / fx[c]))
        lowest = balance = self.eng.ic[(ent, ccy)]
        if upcoming:
            path = balance + pd.concat(upcoming).sort_values("value_date", kind="stable")["amount"].cumsum()
            lowest = min(lowest, float(path.min())) if len(path) else lowest
        floor = self.working_balance(ent, ccy, d)
        return lowest - floor, lowest, floor

    # ---------------- FX ----------------
    def fx_orders(self, d):
        """Internal deals the service companies ask for today.

        Returns [(entity, ccy, amount, value_date, reason)]; amount > 0 = the entity buys ccy
        (against its own currency), amount < 0 = it sells ccy.
        """
        if not is_joint_business_day(d, config.CURRENCIES):
            return []
        eng, conv, orders = self.eng, self.conversion_date(d), []
        window = add_joint_business_days(d, config.FX_HEDGE_LOOKAHEAD_BD, config.CURRENCIES)
        if d < conv <= window and (d.year, d.month) not in self.hedged_months:
            self.hedged_months.add((d.year, d.month))
            for ent, own in self.functional.items():
                for ccy in config.CURRENCIES:
                    if ccy != own:
                        projected = eng.ic[(ent, ccy)] + self._flows(ent, ccy, d, conv)
                        if abs(projected) >= 1:
                            reason = (f"{ent} will be {'short' if projected < 0 else 'long'} {ccy} {abs(projected):,.0f} "
                                      f"on {conv:%d %b} (its balance now plus its known flows to month end). It "
                                      f"converts foreign currency into {own} at month end and fixes the rate now.")
                            orders.append((ent, ccy, -projected, conv, reason))
        elif d == conv:  # whatever is left after today's flows and the forwards: convert at spot
            for ent, own in self.functional.items():
                for ccy in config.CURRENCIES:
                    bal = eng.ic[(ent, ccy)]
                    if ccy != own and abs(bal) >= 1:
                        reason = (f"Month end: {ent} still holds {ccy} {bal:+,.0f} that no forward covered; "
                                  f"converted into {own} at spot.")
                        orders.append((ent, ccy, -bal, d, reason))
        return orders

    def cover(self, d, internal_tickets):
        """External forwards covering today's internal deals, netted per currency and value date.

        Returns [(ccy, amount, value_date, reason)]; amount > 0 = TRS buys ccy against USD.
        Same-day internal deals are left to the flatten step.
        """
        fx, net, count = self.eng.fx.loc[d], defaultdict(float), defaultdict(int)
        for t in internal_tickets:
            if t["value_date"] > d:
                for ccy, amount in self.eng.ticket_legs(t):
                    if ccy != "USD":
                        net[(ccy, t["value_date"])] += amount
                        count[(ccy, t["value_date"])] += 1
        out = []
        for (ccy, vd), amount in sorted(net.items()):
            if abs(amount) / fx[ccy] >= config.MIN_FX_DEAL_USD:
                n = count[(ccy, vd)]
                reason = (f"Today's {n} internal deal{'s leave' if n > 1 else ' leaves'} TRS "
                          f"{'long' if amount > 0 else 'short'} {ccy} {abs(amount):,.0f} for {vd:%d %b}. "
                          "One external forward offsets the net, so TRS stays flat.")
                out.append((ccy, -amount, vd, reason))
        return out

    def flatten(self, d):
        """Spot deals that bring each currency outside the tolerance back to zero: [(ccy, amount, reason)].

        The position counts the interest that accrues until the next business day (a Friday
        includes the weekend), so it stays inside the tolerance until the next check.
        """
        fx, out = self.eng.fx.loc[d], []
        for ccy in config.CURRENCIES[1:]:
            if is_joint_business_day(d, [ccy, "USD"]):
                days = (add_joint_business_days(d, 1, [ccy, "USD"]) - d).days
                position = self.eng.fx_position(ccy) + self.eng.interest_today(d, ccy) * days
                if abs(position) / fx[ccy] > config.FX_TOLERANCE_USD:
                    reason = (f"Open {ccy} position {position:+,.0f} (USD {position / fx[ccy]:+,.0f}, counting "
                              f"interest to the next business day) is outside the ±USD "
                              f"{config.FX_TOLERANCE_USD:,.0f} tolerance: back to zero.")
                    out.append((ccy, -position, reason))
        return out

    # ---------------- IC deposits ----------------
    def ic_deposits(self, d, matured):
        """3-month IC deposits to place today: [(entity, ccy, amount, reason)].

        matured: the (entity, ccy) pairs whose deposit matured today (their money is back on call).
        """
        fx, out = self.eng.fx.loc[d], []
        for ent, ccy in self.functional.items():
            if not is_business_day(d, ccy):
                continue
            if d != nth_business_day(d.year, d.month, 1, ccy) and (ent, ccy) not in matured:
                continue
            surplus, lowest, floor = self.available_for_term(ent, ccy, d)
            if surplus / fx[ccy] >= config.MIN_IC_DEPOSIT_USD:
                amount = math.floor(surplus / config.IC_DEPOSIT_ROUNDING) * config.IC_DEPOSIT_ROUNDING
                why = "A deposit matured today" if (ent, ccy) in matured else "First business day of the month"
                reason = (f"{why}. {ent}'s on-call {ccy} balance is projected to fall no lower than {lowest:,.0f} "
                          f"over the next {config.IC_DEPOSIT_TENOR_MONTHS} months; keeping {floor:,.0f} for about "
                          f"a month of OPEX leaves {surplus:,.0f} that can be locked.")
                out.append((ent, ccy, amount, reason))
        return out

    # ---------------- cash ----------------
    def invest(self, d, ccy):
        """(amount, reason): amount to move into (+) or out of (-) the MMF / call deposit (0 = nothing)."""
        eng, fx = self.eng, self.eng.fx.loc[d, ccy]
        minimum = config.OPERATING_MIN_USD * fx
        excess = eng.cash[ccy] - minimum
        if abs(excess) < config.MIN_INVESTMENT_TRADE_USD * fx:
            return 0.0, None
        if excess < 0:
            excess = -min(-excess, eng.inv[ccy])
        reason = (f"Bank cash {eng.cash[ccy]:,.0f} is {'above' if excess > 0 else 'below'} the "
                  f"{ccy} {minimum:,.0f} operating minimum.")
        return excess, reason

    def projected_low(self, d, ccy):
        """Lowest projected TRS cash in ccy over the look-ahead: today's cash plus the group's
        scheduled flows and the external FX legs that settle in the next business days."""
        horizon = add_joint_business_days(d, config.LOOKAHEAD_BUSINESS_DAYS, [ccy, "USD"])
        events = []
        f = self.flows_by_ccy.get(ccy)
        if f is not None:
            f = f[(f["value_date"] > d) & (f["value_date"] <= horizon)]
            events += list(zip(f["value_date"], f["amount"]))
        for t in self.eng.tickets:
            if not t["is_internal"] and d < t["value_date"] <= horizon:
                events += [(t["value_date"], a) for c, a in self.eng.ticket_legs(t) if c == ccy]
        low = cash = self.eng.cash[ccy]
        for _, amount in sorted(events, key=lambda e: e[0]):
            cash += amount
            low = min(low, cash)
        return low

    def funding_swap(self, d, ccy):
        """(amount, reason): ccy to buy with a USD swap (0 = none) when the projected cash over the
        look-ahead falls below zero and the MMF / deposit cannot cover it. Only on days both markets are open."""
        if ccy == "USD" or not is_joint_business_day(d, [ccy, "USD"]):
            return 0.0, None
        low = self.projected_low(d, ccy)
        short = -(low + self.eng.inv[ccy])
        if short <= 0:
            return 0.0, None
        need = short + config.OPERATING_MIN_USD * self.eng.fx.loc[d, ccy]
        reason = (f"{ccy} bank cash is projected to fall to {low:,.0f} within {config.LOOKAHEAD_BUSINESS_DAYS} "
                  f"business days and the {ccy} investments hold only {self.eng.inv[ccy]:,.0f}. Borrow {ccy} "
                  "against USD for a month instead of selling USD outright, so the FX position does not change.")
        return math.ceil(need / config.FX_SWAP_ROUNDING) * config.FX_SWAP_ROUNDING, reason
