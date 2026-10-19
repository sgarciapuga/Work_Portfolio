"""Phase 2 daily engine: group flows, in-house bank settlement, MMF investing, interest, NAV.

The engine is deterministic: the same inputs always give the same history. Each
run rebuilds the history from config.HISTORY_START, so a daily run and the
backfill always agree; only the new days need to be stored.

Sign conventions
- cash and flows: positive = money in.
- IC current accounts: positive = TRS owes the entity (the entity's cash held at TRS).
- valuation.value_ccy: positive = TRS asset, negative = TRS liability.

Each calendar day d:
1. Scheduled flows hit the entities' currency sub-accounts.
2. Zero-balancing: each sub-account is brought to zero against TRS; the amount
   goes to the entity's IC current account in that currency.
3. On BD2 of the month TRS receives last month's MMF / deposit interest.
4. TRS invests cash above the operating minimum (or redeems to cover a shortfall).
5. Interest accrues on the closing balances (weekends use Friday's rate).
6. On the last day of the month IC interest is posted to the IC accounts.

The daily P&L (pnl_daily) splits the NAV change by source: MMF and deposit
income, IC deposit interest TRS pays, IC loan interest TRS earns, and FX
revaluation of the non-USD NAV. The parts add up to the daily NAV change in USD.
"""

from collections import defaultdict
from datetime import timedelta

import pandas as pd

from tsim import config
from tsim.calendars import is_business_day, nth_business_day
from tsim.rates import ic_deposit_rate, ic_loan_rate, mmf_rate
from tsim.schedule import expand_schedule

IV_DEPOSIT_ID = "ICD-IV-USD-001"

PNL_MMF = "MMF and deposit income"
PNL_IC_DEPOSIT = "IC deposit interest paid"
PNL_IC_LOAN = "IC loan interest earned"
PNL_FX = "FX revaluation"
PNL_COMPONENTS = [PNL_MMF, PNL_IC_DEPOSIT, PNL_IC_LOAN, PNL_FX]


def fx_daily(fx_rows, start, end):
    """Units of currency per 1 USD for every calendar day (gaps carry the last rate)."""
    df = fx_rows.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    wide = df.pivot_table(index="date", columns="currency", values="fx_to_usd")
    days = pd.date_range(start - timedelta(days=10), end, freq="D").date
    wide = wide.reindex(days).ffill().bfill()
    wide["USD"] = 1.0
    missing = [c for c in config.CURRENCIES if c not in wide.columns or wide[c].isna().any()]
    if missing:
        raise ValueError(f"No FX rates for {missing}")
    return wide.loc[start:end, config.CURRENCIES]


def _month_key(d):
    return d.year, d.month


def _is_month_end(d):
    return (d + timedelta(days=1)).month != d.month


class Engine:
    def __init__(self, static, on_rates, fx, start, end, vary=True):
        self.static, self.on, self.fx = static, on_rates, fx
        self.start, self.end = start, end
        acc = static["accounts"]
        self.entity_accounts = acc[(acc["entity_code"] != "TRS") & (acc["account_type"] == "operating")]
        self.account_of = {(r.entity_code, r.currency): r.account_id for r in self.entity_accounts.itertuples()}
        self.flows = expand_schedule(static["fee_schedule"], start, end, vary=vary)
        self.basis = config.DAY_COUNT_BASIS
        self.out = defaultdict(list)
        self._seq = 0
        self._open()

    # ---------------- opening position ----------------
    def _open(self):
        d, fx = self.start, self.fx.loc[self.start]
        self.entity_cash = {a: 0.0 for a in self.entity_accounts["account_id"]}
        self.ic = defaultdict(float)
        for (ent, ccy), amt in config.OPENING_IC_CURRENT_ACCOUNTS.items():
            self.ic[(ent, ccy)] = float(amt)
        self.ic_accrued = defaultdict(float)
        self.iv_dep, self.iv_accrued = float(config.OPENING_IV_DEPOSIT_USD), 0.0
        self.inv_accrued = defaultdict(float)  # (ccy, (year, month)) -> interest not yet paid
        self.cash, self.inv = {}, {}
        for ccy in config.CURRENCIES:
            target = config.OPERATING_MIN_USD * fx[ccy]
            funding = sum(v for (e, c), v in self.ic.items() if c == ccy)
            if ccy == "USD":
                funding += self.iv_dep + config.TRS_EQUITY_USD
            self.cash[ccy] = target
            self.inv[ccy] = funding - target
        self.prev_nav, self.prev_fx = None, None
        self.out["opening"].append({"date": d, **{f"inv_{c}": self.inv[c] for c in config.CURRENCIES}})

    # ---------------- helpers ----------------
    def _txn(self, d, account, flow_code, ccy, amount, counterparty=None, cp_entity=None, ic=False, position=None):
        self._seq += 1
        self.out["cash_txn"].append({
            "txn_id": f"T{d:%Y%m%d}-{self._seq:06d}", "value_date": d, "account_id": account,
            "flow_code": flow_code, "currency": ccy, "amount": round(amount, 2), "counterparty": counterparty,
            "counterparty_entity": cp_entity, "is_intercompany": ic, "position_id": position, "deal_id": None,
        })

    # ---------------- daily steps ----------------
    def _group_flows(self, d):
        for f in self.flows[self.flows["value_date"] == d].itertuples():
            acct = self.account_of[(f.entity_code, f.currency)]
            self.entity_cash[acct] += f.amount
            self._txn(d, acct, f.flow_code, f.currency, f.amount, f.counterparty, f.counterparty_entity,
                      ic=f.counterparty_entity is not None)

    def _zero_balance(self, d, settled):
        for r in self.entity_accounts.itertuples():
            amt = self.entity_cash[r.account_id]
            if abs(amt) < 0.005:
                continue
            main = config.TRS_MAIN_ACCOUNT[r.currency]
            self._txn(d, r.account_id, "IHB_SETTLE", r.currency, -amt, "TRS", "TRS", ic=True)
            self._txn(d, main, "IHB_SETTLE", r.currency, amt, r.entity_code, r.entity_code, ic=True)
            self.entity_cash[r.account_id] = 0.0
            self.cash[r.currency] += amt
            self.ic[(r.entity_code, r.currency)] += amt
            settled[(r.entity_code, r.currency)] += amt

    def _pay_investment_interest(self, d, ccy):
        if d != nth_business_day(d.year, d.month, config.MMF_INTEREST_PAY_BD, ccy):
            return
        due = [k for k in self.inv_accrued if k[0] == ccy and k[1] < _month_key(d)]
        amt = sum(self.inv_accrued.pop(k) for k in due)
        if amt:
            code = "DEP_INT" if ccy == "CHF" else "MMF_INT"
            self.cash[ccy] += amt
            self._txn(d, config.TRS_MAIN_ACCOUNT[ccy], code, ccy, amt, config.INVESTMENT_ACCOUNT[ccy],
                      position=config.INVESTMENT_ACCOUNT[ccy])

    def _invest(self, d, ccy):
        fx = self.fx.loc[d, ccy]
        excess = self.cash[ccy] - config.OPERATING_MIN_USD * fx
        if abs(excess) < config.MIN_INVESTMENT_TRADE_USD * fx:
            return
        if excess < 0:
            excess = -min(-excess, self.inv[ccy])
            if excess == 0:
                return
        sub, red = ("DEP_PLACE", "DEP_RETURN") if ccy == "CHF" else ("MMF_SUB", "MMF_RED")
        self.cash[ccy] -= excess
        self.inv[ccy] += excess
        self._txn(d, config.TRS_MAIN_ACCOUNT[ccy], sub if excess > 0 else red, ccy, -excess,
                  config.INVESTMENT_ACCOUNT[ccy], position=config.INVESTMENT_ACCOUNT[ccy])

    def _accrue(self, d):
        """Accrue one day of interest; returns {(ccy, component): amount in ccy} (+ = TRS income)."""
        pnl = defaultdict(float)
        for ccy in config.CURRENCIES:
            on, basis = self.on.loc[d, ccy], self.basis[ccy]
            income = self.inv[ccy] * mmf_rate(on) / basis
            self.inv_accrued[(ccy, _month_key(d))] += income
            pnl[(ccy, PNL_MMF)] += income
            for (ent, c), bal in list(self.ic.items()):
                if c == ccy and bal:
                    rate = ic_deposit_rate(on) if bal > 0 else ic_loan_rate(on)
                    interest = bal * rate / basis          # + = TRS owes more (cost), - = entity owes more (income)
                    self.ic_accrued[(ent, c)] += interest
                    pnl[(ccy, PNL_IC_DEPOSIT if bal > 0 else PNL_IC_LOAN)] -= interest
        iv_interest = self.iv_dep * ic_deposit_rate(self.on.loc[d, "USD"]) / self.basis["USD"]
        self.iv_accrued += iv_interest
        pnl[("USD", PNL_IC_DEPOSIT)] -= iv_interest
        return pnl

    def _post_ic_interest(self, d, posted):
        for key, amt in list(self.ic_accrued.items()):
            self.ic[key] += amt
            posted[key] += amt
            self.ic_accrued[key] = 0.0
        self.iv_dep += self.iv_accrued
        self.iv_accrued = 0.0

    # ---------------- records ----------------
    def _record_pnl(self, d, pnl):
        fx = self.fx.loc[d]
        for ccy in config.CURRENCIES:
            for comp in PNL_COMPONENTS[:3]:
                amt = pnl.get((ccy, comp), 0.0)
                self.out["pnl_daily"].append({"pnl_date": d, "currency": ccy, "component": comp,
                                              "amount_ccy": round(amt, 2), "amount_usd": round(amt / fx[ccy], 2)})
            # FX revaluation: yesterday's NAV in the currency, valued at today's rate instead of yesterday's
            reval = 0.0
            if self.prev_nav is not None and ccy != "USD":
                reval = self.prev_nav[ccy] * (1 / fx[ccy] - 1 / self.prev_fx[ccy])
            self.out["pnl_daily"].append({"pnl_date": d, "currency": ccy, "component": PNL_FX,
                                          "amount_ccy": 0.0, "amount_usd": round(reval, 2)})

    def _record(self, d, opening_ic, settled, posted, opening_cash):
        fx = self.fx.loc[d]
        nav_today = {}
        for r in self.static["accounts"].itertuples():
            if r.entity_code == "TRS":
                if r.account_id in config.TRS_MAIN_ACCOUNT.values():
                    close = self.cash[r.currency]
                    op = opening_cash[r.currency]
                elif r.account_id == config.INVESTMENT_ACCOUNT["CHF"]:
                    close, op = self.inv["CHF"], opening_cash["CHF-DEP"]
                else:
                    close = op = 0.0
            else:
                close = op = 0.0  # zero-balanced every day
            self.out["cash_balance"].append({"balance_date": d, "account_id": r.account_id, "opening": round(op, 2),
                                             "movements": round(close - op, 2), "closing": round(close, 2)})
        for (ent, ccy) in sorted(set(self.ic) | set(self.account_of)):
            if ent == "TRS":
                continue
            self.out["ic_current_account"].append({
                "balance_date": d, "entity_code": ent, "currency": ccy,
                "opening": round(opening_ic.get((ent, ccy), 0.0), 2), "settlements": round(settled[(ent, ccy)], 2),
                "interest_posted": round(posted[(ent, ccy)], 2), "closing": round(self.ic[(ent, ccy)], 2),
                "accrued_interest": round(self.ic_accrued[(ent, ccy)], 2)})
        for ccy in config.CURRENCIES:
            pos = config.INVESTMENT_ACCOUNT[ccy]
            accrued = sum(v for k, v in self.inv_accrued.items() if k[0] == ccy)
            value = self.inv[ccy] + accrued
            self.out["valuation"].append({"valuation_date": d, "item_type": "position", "item_id": pos,
                                          "currency": ccy, "accrued_interest": round(accrued, 2), "mtm": 0.0,
                                          "value_ccy": round(value, 2), "value_usd": round(value / fx[ccy], 2)})
        iv_value = -(self.iv_dep + self.iv_accrued)
        self.out["valuation"].append({"valuation_date": d, "item_type": "position", "item_id": IV_DEPOSIT_ID,
                                      "currency": "USD", "accrued_interest": round(-self.iv_accrued, 2), "mtm": 0.0,
                                      "value_ccy": round(iv_value, 2), "value_usd": round(iv_value, 2)})
        for ccy in config.CURRENCIES:
            inv_acc = sum(v for k, v in self.inv_accrued.items() if k[0] == ccy)
            ic_bal = [self.ic[k] + self.ic_accrued[k] for k in self.ic if k[1] == ccy]
            assets = max(self.cash[ccy], 0) + self.inv[ccy] + inv_acc + sum(-b for b in ic_bal if b < 0)
            liabilities = max(-self.cash[ccy], 0) + sum(b for b in ic_bal if b > 0)
            if ccy == "USD":
                liabilities += self.iv_dep + self.iv_accrued
            nav = assets - liabilities
            nav_today[ccy] = nav
            self.out["nav_daily"].append({
                "nav_date": d, "currency": ccy, "assets": round(assets, 2), "liabilities": round(liabilities, 2),
                "nav_ccy": round(nav, 2), "nav_usd": round(nav / fx[ccy], 2),
                "open_fx_position_ccy": 0.0 if ccy == "USD" else round(nav, 2),
                "open_fx_position_usd": 0.0 if ccy == "USD" else round(nav / fx[ccy], 2)})
            if self.cash[ccy] < -0.005:
                self.out["alerts"].append({"alert_date": d, "currency": ccy, "alert": "overdraft",
                                           "amount": round(self.cash[ccy], 2)})
        self.prev_nav, self.prev_fx = nav_today, fx

    # ---------------- run ----------------
    def run(self):
        d = self.start
        while d <= self.end:
            opening_ic = dict(self.ic)
            opening_cash = {**self.cash, "CHF-DEP": self.inv["CHF"]}
            settled, posted = defaultdict(float), defaultdict(float)
            self._group_flows(d)
            self._zero_balance(d, settled)
            for ccy in config.CURRENCIES:
                if is_business_day(d, ccy):
                    self._pay_investment_interest(d, ccy)
                    self._invest(d, ccy)
            pnl = self._accrue(d)
            if _is_month_end(d):
                self._post_ic_interest(d, posted)
            self._record_pnl(d, pnl)
            self._record(d, opening_ic, settled, posted, opening_cash)
            d += timedelta(days=1)
        return self.results()

    def results(self):
        tables = {name: pd.DataFrame(rows) for name, rows in self.out.items()}
        tables.setdefault("alerts", pd.DataFrame(columns=["alert_date", "currency", "alert", "amount"]))
        tables["position"] = self._positions()
        return tables

    def _positions(self):
        rows = []
        for ccy in config.CURRENCIES:
            pos = config.INVESTMENT_ACCOUNT[ccy]
            rows.append({"position_id": pos, "position_type": "DEPOSIT" if ccy == "CHF" else "MMF",
                         "counterparty": pos, "currency": ccy, "principal": round(self.inv[ccy], 2),
                         "rate": None, "start_date": self.start, "maturity_date": None, "status": "open",
                         "facility_id": None, "fund_id": None if ccy == "CHF" else pos, "linked_position_id": None})
        rows.append({"position_id": IV_DEPOSIT_ID, "position_type": "IC_DEPOSIT", "counterparty": "IV",
                     "currency": "USD", "principal": round(self.iv_dep, 2), "rate": None, "start_date": self.start,
                     "maturity_date": None, "status": "open", "facility_id": None, "fund_id": None,
                     "linked_position_id": None})
        return pd.DataFrame(rows)


def run_engine(static, on_rates, fx, start, end, vary=True):
    return Engine(static, on_rates, fx, start, end, vary=vary).run()
