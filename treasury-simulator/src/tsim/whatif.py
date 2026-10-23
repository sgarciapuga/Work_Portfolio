"""Play treasurer (Phase 3b): take one day's decisions yourself and compare with the autopilot.

The engine runs the history to the close of the day before the decision day. From there two
copies go on: one with the autopilot's decisions, one with yours on the decision day (the
autopilot takes over again the day after). Both run to the same horizon on the same rates:
the real rates for a past day (a replay), the latest rates held flat after the last closed day.

Decisions are keyed so a page can show them as a form:
    cover|GBP|2026-10-30   external forward covering the entities' deals (amount: + TRS buys)
    spot|GBP               the autopilot's spot to flatten a currency
    extra_spot|GBP         your own spot deal (+ TRS buys, - TRS sells), not proposed by the autopilot
    deposit|MGT|GBP        3-month IC deposit placed by a service company on TRS's advice
    invest|EUR             into (+) or out of (-) the currency's MMF / call deposit
    swap|CHF               currency bought today against USD and sold back in a month
An amount of 0 skips the decision. On your day only the decisions you pass are taken: a key you
leave out counts as skipped (use your_day() to start from the autopilot's proposals).
"""

import copy
from datetime import timedelta

import pandas as pd

from tsim import config
from tsim.autopilot import Autopilot
from tsim.engine import Engine


class DecisionDay(Autopilot):
    """The autopilot, except on `day`: it records its proposals there and, given overrides, takes yours."""

    def __init__(self, autopilot, day, overrides=None):
        self.__dict__.update(autopilot.__dict__)   # same engine, same state
        self.day, self.overrides, self.proposals = day, overrides, []

    def _decide(self, d, key, kind, label, ccy, proposed, reason):
        if d != self.day:
            return proposed, reason
        self.proposals.append({"key": key, "kind": kind, "label": label, "currency": ccy,
                               "proposed": round(float(proposed), 2), "reason": reason})
        if self.overrides is None:
            return proposed, reason
        # your day is yours: a decision you were not shown (e.g. a spot the autopilot would add after you
        # skipped a cover) is not taken; the autopilot takes over again the next day
        mine = float(self.overrides.get(key, 0.0))
        if abs(mine - proposed) < 0.005:
            return proposed, reason
        return mine, f"Your decision (the autopilot proposed {proposed:,.0f})."

    def cover(self, d, internal_tickets):
        out = []
        for ccy, amount, vd, reason in super().cover(d, internal_tickets):
            amt, why = self._decide(d, f"cover|{ccy}|{vd}", "Cover forward",
                                    f"Forward with {config.FX_BANK}: TRS buys (+) / sells (-) {ccy}, value {vd:%d %b}",
                                    ccy, amount, reason)
            if amt:
                out.append((ccy, amt, vd, why))
        return out

    def flatten(self, d):
        out = []
        for ccy, amount, reason in super().flatten(d):
            amt, why = self._decide(d, f"spot|{ccy}", "Spot to flatten",
                                    f"Spot with {config.FX_BANK}: TRS buys (+) / sells (-) {ccy}", ccy, amount, reason)
            if amt:
                out.append((ccy, amt, why))
        if d == self.day:
            for ccy in config.CURRENCIES[1:]:
                amt, _ = self._decide(d, f"extra_spot|{ccy}", "Your own spot",
                                      f"Extra spot with {config.FX_BANK}: TRS buys (+) / sells (-) {ccy}", ccy, 0.0,
                                      None)
                if amt:
                    out.append((ccy, amt, "Your own spot deal."))
        return out

    def ic_deposits(self, d, matured):
        out = []
        for ent, ccy, amount, reason in super().ic_deposits(d, matured):
            amt, why = self._decide(d, f"deposit|{ent}|{ccy}", "IC term deposit",
                                    f"{ent} places a 3-month deposit ({ccy})", ccy, amount, reason)
            if amt > 0:
                out.append((ent, ccy, amt, why))
        return out

    def invest(self, d, ccy):
        amount, reason = super().invest(d, ccy)
        amt, why = self._decide(d, f"invest|{ccy}", "Invest / redeem",
                                f"{config.INVESTMENT_ACCOUNT[ccy]}: invest (+) / redeem (-) {ccy}", ccy, amount, reason)
        return max(amt, -self.eng.inv[ccy]), why   # cannot redeem more than is invested

    def funding_swap(self, d, ccy):
        amount, reason = super().funding_swap(d, ccy)
        if not amount and d == self.day and not (self.overrides or {}).get(f"swap|{ccy}"):
            return amount, reason   # nothing proposed or asked: no form row
        amt, why = self._decide(d, f"swap|{ccy}", "Funding swap",
                                f"1-month swap: buy {ccy} today against USD, sell it back", ccy, amount, reason)
        return max(amt, 0.0), why


def setup(static, on_rates, fx, start, day, until, vary=True):
    """The engine at the close of the day before `day`, ready to play `day` and go on to `until`.
    on_rates and fx must cover the days up to `until` (hold the last values for future days)."""
    eng = Engine(static, on_rates, fx, start, until, vary=vary)
    eng.run_until(day - timedelta(days=1))
    eng.clear_outputs()
    return eng


def _copy_with(base, day, overrides):
    eng = copy.deepcopy(base)
    eng.autopilot = DecisionDay(eng.autopilot, day, overrides)
    return eng


def proposals(base, day):
    """(the autopilot's proposals for `day` as a DataFrame, the engine outputs of that day)."""
    eng = _copy_with(base, day, None)
    eng.run_until(day)
    return pd.DataFrame(eng.autopilot.proposals, columns=["key", "kind", "label", "currency", "proposed", "reason"]), \
        eng.results()


def your_day(props, **changes):
    """Your decisions: the autopilot's proposals, with some changed. Keys use '|' (pass them as a dict:
    your_day(props, **{"cover|GBP|2025-01-31": 0}))."""
    decisions = dict(zip(props["key"], props["proposed"]))
    decisions.update(changes)
    return decisions


def play(base, day, until, overrides=None):
    """Engine outputs from `day` to `until`: the autopilot's (overrides=None) or with yours on `day`."""
    eng = _copy_with(base, day, overrides)
    eng.run_until(until)
    return eng.results()


def compare(auto, mine, fx, day, shock=0.02):
    """Side-by-side measures for two plays over the same window. fx: units per USD by date."""
    def measures(res):
        nav = res["nav_daily"]
        end = nav["nav_date"].max()
        alerts = res["alerts"]
        bal = res["cash_balance"]
        main = bal[bal["account_id"].isin(config.TRS_MAIN_ACCOUNT.values())].copy()
        main["ccy"] = main["account_id"].str[-3:]
        rate = [fx.loc[d, c] for d, c in zip(main["balance_date"], main["ccy"])]
        main["idle_usd"] = ((main["closing"] - config.OPERATING_MIN_USD * pd.Series(rate, index=main.index)).clip(lower=0)
                            / pd.Series(rate, index=main.index))
        first = nav[(nav["nav_date"] == day) & (nav["currency"] != "USD")]
        pnl = res["pnl_daily"].groupby("component")["amount_usd"].sum()
        row = {
            "NAV at the end (USD)": nav.loc[nav["nav_date"] == end, "nav_usd"].sum(),
            "P&L over the period (USD)": pnl.sum(),
            "of which interest (USD)": pnl.drop(["FX revaluation", "FX deal MTM"], errors="ignore").sum(),
            "of which FX (USD)": pnl.reindex(["FX revaluation", "FX deal MTM"]).fillna(0).sum(),
            "Largest open FX (USD)": nav.loc[nav["currency"] != "USD", "open_fx_position_usd"].abs().max(),
            "Days outside FX tolerance": alerts.loc[alerts["alert"] == "fx_outside_tolerance", "alert_date"].nunique()
            if len(alerts) else 0,
            "Days with an overdraft": alerts.loc[alerts["alert"] == "overdraft", "alert_date"].nunique()
            if len(alerts) else 0,
            "Average idle cash (USD)": main.groupby("balance_date")["idle_usd"].sum().mean(),
            f"Loss if FX moves {shock:.0%} against TRS (USD)": first["open_fx_position_usd"].abs().sum() * shock,
        }
        return row

    a, m = measures(auto), measures(mine)
    better_high = {"NAV at the end (USD)", "P&L over the period (USD)", "of which interest (USD)", "of which FX (USD)"}
    rows = [{"Measure": k, "Autopilot": a[k], "Yours": m[k], "Difference": m[k] - a[k],
             "Better when": "higher" if k in better_high else "lower"} for k in a]
    return pd.DataFrame(rows)
