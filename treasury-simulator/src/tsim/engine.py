"""Daily engine: group flows, in-house bank settlement, the autopilot's decisions, interest, MTM, NAV.

The engine is deterministic: the same inputs always give the same history. Each
run rebuilds the history from config.HISTORY_START, so a daily run and the
backfill always agree; only the new days need to be stored. The engine does the
bookkeeping; the decisions come from the autopilot (tsim.autopilot).

Sign conventions
- cash and flows: positive = money in.
- IC current accounts: positive = TRS owes the entity (the entity's cash held at TRS).
- valuation.value_ccy: positive = TRS asset, negative = TRS liability.
- FX deals are stored from TRS's side: TRS buys buy_amount of buy_ccy and sells sell_amount of sell_ccy.

Each calendar day d:
1. Scheduled flows hit the entities' currency sub-accounts.
2. Zero-balancing: each sub-account is brought to zero against TRS; the amount
   goes to the entity's IC current account in that currency.
3. FX deals with value date d settle: external deals on TRS's bank accounts,
   internal deals on the entity's IC current accounts.
4. IC term deposits maturing on d go back on call, with their interest.
5. Autopilot: new IC term deposits; MMF interest on BD2 and invest or divest (EUR,
   GBP, CHF); the entities' FX orders (internal deals), TRS's cover of the net with
   external forwards, and spot to flatten anything outside the tolerance; a funding
   swap for a currency the look-ahead shows short; then MMF interest and invest or
   divest in USD, last because swaps move USD.
6. Interest accrues on the closing balances (weekends use Friday's rate), and
   open FX deals are revalued (MTM, undiscounted).
7. On the last day of the month IC current account interest is posted.

Every decision (with the autopilot's reason) and every scheduled event (deal
settlements, deposit maturities, interest received or posted) is written to the
treasurer's log (activity): one plain-English line each.

The daily P&L (pnl_daily) splits the NAV change by source: MMF and deposit income,
IC deposit interest TRS pays, IC loan interest TRS earns, FX revaluation of the
non-USD balance sheet, and the change in MTM of the FX deals. The parts add up to
the daily NAV change in USD; when TRS is flat, the last two largely cancel.
"""

from collections import defaultdict
from datetime import timedelta

import pandas as pd

from tsim import config
from tsim.autopilot import Autopilot
from tsim.calendars import add_joint_business_days, add_months, is_business_day, nth_business_day
from tsim.market import deal_rate, forward_fx_to_usd
from tsim.rates import ic_deposit_rate, ic_loan_rate, mmf_rate
from tsim.schedule import expand_schedule

IV_DEPOSIT_ID = "ICD-IV-USD-001"

PNL_MMF = "MMF and deposit income"
PNL_IC_DEPOSIT = "IC deposit interest paid"
PNL_IC_LOAN = "IC loan interest earned"
PNL_FX = "FX revaluation"
PNL_FX_DEALS = "FX deal MTM"
PNL_COMPONENTS = [PNL_MMF, PNL_IC_DEPOSIT, PNL_IC_LOAN, PNL_FX, PNL_FX_DEALS]

FX_DEAL_COLUMNS = ["deal_id", "leg", "deal_type", "trade_date", "value_date", "buy_ccy", "buy_amount", "sell_ccy",
                   "sell_amount", "rate", "counterparty", "is_internal"]
ACTIVITY_COLUMNS = ["activity_date", "seq", "kind", "category", "entity_code", "currency", "amount", "ref",
                    "description", "reason"]
FX_FLOW_CODE = {("spot", "single"): "FX_SPOT", ("forward", "single"): "FX_FWD",
                ("swap", "near"): "FX_SWAP_NEAR", ("swap", "far"): "FX_SWAP_FAR"}


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
        # beyond `end` too: the autopilot projects ahead; only flows up to `end` are booked
        self.flows = expand_schedule(static["fee_schedule"], start, end + timedelta(days=config.PROJECTION_HORIZON_DAYS),
                                     vary=vary)
        self.basis = config.DAY_COUNT_BASIS
        self.out = defaultdict(list)
        self._seq = 0
        self._deal_seq = defaultdict(int)
        self.tickets = []          # open FX deal legs (TRS side)
        self.terms = {}            # IC term deposits / loans: position_id -> dict
        self._fx_pnl = defaultdict(float)
        self._log_seq = defaultdict(int)
        self._open()
        self.autopilot = Autopilot(self)

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
    def _txn(self, d, account, flow_code, ccy, amount, counterparty=None, cp_entity=None, ic=False, position=None,
             deal=None):
        self._seq += 1
        self.out["cash_txn"].append({
            "txn_id": f"T{d:%Y%m%d}-{self._seq:06d}", "value_date": d, "account_id": account,
            "flow_code": flow_code, "currency": ccy, "amount": round(amount, 2), "counterparty": counterparty,
            "counterparty_entity": cp_entity, "is_intercompany": ic, "position_id": position, "deal_id": deal,
        })

    def _log(self, d, kind, category, description, reason=None, entity=None, ccy=None, amount=None, ref=None):
        """One line of the treasurer's log. kind: 'action' (a decision) or 'event' (something scheduled)."""
        self._log_seq[d] += 1
        self.out["activity"].append({
            "activity_date": d, "seq": self._log_seq[d], "kind": kind, "category": category,
            "entity_code": entity, "currency": ccy, "amount": None if amount is None else round(amount, 2),
            "ref": ref, "description": description, "reason": reason})

    @staticmethod
    def _deal_text(t):
        return (f"{t['buy_ccy']} {t['buy_amount']:,.0f} against {t['sell_ccy']} {t['sell_amount']:,.0f} "
                f"at {t['rate']:.4f}")

    def _fwd(self, d, ccy, value_date):
        """Units of ccy per 1 USD for value_date, seen on day d."""
        return forward_fx_to_usd(self.fx.loc[d, ccy], self.on.loc[d, ccy], self.on.loc[d, "USD"], ccy,
                                 (value_date - d).days)

    @staticmethod
    def ticket_legs(t):
        """[(ccy, amount)] from TRS's side: + = TRS receives, - = TRS pays."""
        return [(t["buy_ccy"], t["buy_amount"]), (t["sell_ccy"], -t["sell_amount"])]

    def _leg_values(self, d, t):
        """USD value of each leg of an open ticket on day d (undiscounted)."""
        return {ccy: amount / self._fwd(d, ccy, max(t["value_date"], d)) for ccy, amount in self.ticket_legs(t)}

    def fx_position(self, ccy):
        """Net open position in ccy: balance sheet + the legs of open FX deals."""
        assets, liabilities = self._balance_sheet(ccy)
        legs = sum(a for t in self.tickets for c, a in self.ticket_legs(t) if c == ccy)
        return assets - liabilities + legs

    # ---------------- FX deals ----------------
    def book_fx(self, d, deal_type, ccy, amount, value_date, counterparty, internal, counter_ccy="USD",
                leg="single", deal_id=None):
        """Book one deal leg: TRS buys `amount` of ccy (sells if negative) against counter_ccy, at the
        forward rate for value_date (spot if value_date = d), so its MTM is zero when booked."""
        if deal_id is None:
            self._deal_seq[d] += 1
            deal_id = f"{'FXI' if internal else 'FXE'}{d:%Y%m%d}-{self._deal_seq[d]:03d}"
        counter = abs(amount) * self._fwd(d, counter_ccy, value_date) / self._fwd(d, ccy, value_date)
        buy, sell = ((ccy, abs(amount)), (counter_ccy, counter)) if amount > 0 else ((counter_ccy, counter),
                                                                                     (ccy, abs(amount)))
        t = {"deal_id": deal_id, "leg": leg, "deal_type": deal_type, "trade_date": d, "value_date": value_date,
             "buy_ccy": buy[0], "buy_amount": round(buy[1], 2), "sell_ccy": sell[0], "sell_amount": round(sell[1], 2),
             "counterparty": counterparty, "is_internal": internal}
        t["rate"] = round(deal_rate(t["buy_ccy"], t["buy_amount"], t["sell_ccy"], t["sell_amount"]), 8)
        self.out["fx_deal"].append({k: t[k] for k in FX_DEAL_COLUMNS})
        t["last"] = self._leg_values(d, t)
        self.tickets.append(t)
        return t

    def _settle_ticket(self, d, t, transfers, log=True):
        fx = self.fx.loc[d]
        if log:
            where = f"on {t['counterparty']}'s IC current accounts" if t["is_internal"] else "on TRS's bank accounts"
            leg = "" if t["leg"] == "single" else f" ({t['leg']} leg)"
            self._log(d, "event", "FX", f"{t['deal_id']}{leg} settles {where}: TRS receives {t['buy_ccy']} "
                      f"{t['buy_amount']:,.0f} and pays {t['sell_ccy']} {t['sell_amount']:,.0f}.",
                      entity=t["counterparty"] if t["is_internal"] else None, ref=t["deal_id"])
        for ccy, amount in self.ticket_legs(t):
            if t["is_internal"]:
                self.ic[(t["counterparty"], ccy)] -= amount
                transfers[(t["counterparty"], ccy)] -= amount
            else:
                self.cash[ccy] += amount
                self._txn(d, config.TRS_MAIN_ACCOUNT[ccy], FX_FLOW_CODE[(t["deal_type"], t["leg"])], ccy, amount,
                          t["counterparty"], deal=t["deal_id"])
            self._fx_pnl[ccy] += amount / fx[ccy] - t["last"][ccy]
        self.tickets.remove(t)

    def _settle_fx(self, d, transfers):
        for t in [t for t in self.tickets if t["value_date"] <= d]:
            self._settle_ticket(d, t, transfers)

    def _fx_decisions(self, d, transfers):
        ap = self.autopilot
        internal = []
        for ent, ccy, amount, value_date, reason in ap.fx_orders(d):
            own = ap.functional[ent]
            deal_type = "spot" if value_date == d else "forward"
            # the entity buys `amount` of ccy, so TRS sells it
            t = self.book_fx(d, deal_type, ccy, -amount, value_date, ent, True, counter_ccy=own)
            internal.append(t)
            self._log(d, "action", "FX", f"{ent} {'buys' if amount > 0 else 'sells'} {ccy} {abs(amount):,.0f} "
                      f"{'from' if amount > 0 else 'to'} TRS against {own}, {deal_type} value {value_date:%d %b} "
                      f"({t['deal_id']}: TRS buys {self._deal_text(t)}).", reason, ent, ccy, amount, t["deal_id"])
        for ccy, amount, value_date, reason in ap.cover(d, internal):
            t = self.book_fx(d, "forward", ccy, amount, value_date, config.FX_BANK, False)
            self._log(d, "action", "FX", f"TRS {'buys' if amount > 0 else 'sells'} {ccy} {abs(amount):,.0f} forward "
                      f"{'from' if amount > 0 else 'to'} {config.FX_BANK}, value {value_date:%d %b} "
                      f"({t['deal_id']}: {self._deal_text(t)}).", reason, None, ccy, amount, t["deal_id"])
        for t in [t for t in internal if t["value_date"] == d]:
            self._settle_ticket(d, t, transfers, log=False)   # same-day: the action line says it all
        for ccy, amount, reason in ap.flatten(d):
            value_date = add_joint_business_days(d, config.SPOT_DAYS, [ccy, "USD"])
            t = self.book_fx(d, "spot", ccy, amount, value_date, config.FX_BANK, False)
            self._log(d, "action", "FX", f"TRS {'buys' if amount > 0 else 'sells'} {ccy} {abs(amount):,.0f} spot "
                      f"{'from' if amount > 0 else 'to'} {config.FX_BANK}, value {value_date:%d %b} "
                      f"({t['deal_id']}: {self._deal_text(t)}).", reason, None, ccy, amount, t["deal_id"])

    def _funding_swap(self, d, ccy, transfers):
        amount, reason = self.autopilot.funding_swap(d, ccy)
        if amount:
            far = add_months(d, config.SWAP_TENOR_MONTHS, [ccy, "USD"])
            near = self.book_fx(d, "swap", ccy, amount, d, config.FX_BANK, False, leg="near")
            self.book_fx(d, "swap", ccy, -amount, far, config.FX_BANK, False, leg="far", deal_id=near["deal_id"])
            self._settle_ticket(d, near, transfers, log=False)
            self._log(d, "action", "FX", f"TRS buys {ccy} {amount:,.0f} today and sells it back on {far:%d %b} "
                      f"({near['deal_id']}: 1-month swap against USD {near['sell_amount']:,.0f}).", reason, None, ccy,
                      amount, near["deal_id"])

    def _revalue_fx(self, d):
        """Daily MTM of open deals; the change per currency goes to P&L. Returns MTM (USD) per deal."""
        mtm = defaultdict(float)
        for t in self.tickets:
            values = self._leg_values(d, t)
            for ccy, v in values.items():
                self._fx_pnl[ccy] += v - t["last"][ccy]
                mtm[t["deal_id"]] += v
            t["last"] = values
        return mtm

    # ---------------- IC term deposits ----------------
    def _mature_terms(self, d, transfers):
        matured = set()
        for pid, p in self.terms.items():
            if p["status"] == "open" and p["maturity_date"] <= d:
                amount = p["principal"] + p["accrued"]
                sign = 1 if p["position_type"] == "IC_DEPOSIT" else -1
                self.ic[(p["counterparty"], p["currency"])] += sign * amount
                transfers[(p["counterparty"], p["currency"])] += sign * amount
                self._log(d, "event", "Deposits", f"{pid} matures: {p['currency']} {amount:,.0f} (principal "
                          f"{p['principal']:,.0f} + interest {p['accrued']:,.0f}) goes back on {p['counterparty']}'s "
                          "on-call account.", entity=p["counterparty"], ccy=p["currency"], amount=amount, ref=pid)
                p["accrued"], p["status"] = 0.0, "repaid"
                matured.add((p["counterparty"], p["currency"]))
        return matured

    def _place_terms(self, d, matured, transfers):
        for ent, ccy, amount, reason in self.autopilot.ic_deposits(d, matured):
            pid = f"ICD-{ent}-{ccy}-{d:%Y%m%d}"
            rate = ic_deposit_rate(self.on.loc[d, ccy]) + config.IC_TERM_PREMIUM_BP / 10_000
            maturity = add_months(d, config.IC_DEPOSIT_TENOR_MONTHS, [ccy])
            self.terms[pid] = {"position_type": "IC_DEPOSIT", "counterparty": ent, "currency": ccy,
                               "principal": float(amount), "rate": rate, "start_date": d,
                               "maturity_date": maturity, "accrued": 0.0, "status": "open"}
            self.ic[(ent, ccy)] -= amount
            transfers[(ent, ccy)] -= amount
            rolled = ""
            for old, p in self.terms.items():   # the deposit that matured today was rolled into this one
                if (p["counterparty"], p["currency"]) == (ent, ccy) and p["maturity_date"] == d:
                    p["status"], rolled = "rolled", f", rolling {old}"
            self._log(d, "action", "Deposits", f"{ent} places {ccy} {amount:,.0f} with TRS for "
                      f"{config.IC_DEPOSIT_TENOR_MONTHS} months at a fixed {rate:.3%}, maturing {maturity:%d %b %Y} "
                      f"({pid}{rolled}).", reason, ent, ccy, amount, pid)

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
            months = ", ".join(f"{pd.Timestamp(year=y, month=m, day=1):%b %Y}" for _, (y, m) in sorted(due))
            self._log(d, "event", "Interest", f"TRS receives {ccy} {amt:,.0f} interest on "
                      f"{config.INVESTMENT_ACCOUNT[ccy]} for {months} (paid on business day "
                      f"{config.MMF_INTEREST_PAY_BD}).", ccy=ccy, amount=amt, ref=config.INVESTMENT_ACCOUNT[ccy])

    def _invest_step(self, d, ccy):
        if is_business_day(d, ccy):
            self._pay_investment_interest(d, ccy)
            self._invest(d, ccy)

    def _invest(self, d, ccy):
        excess, reason = self.autopilot.invest(d, ccy)
        if not excess:
            return
        sub, red = ("DEP_PLACE", "DEP_RETURN") if ccy == "CHF" else ("MMF_SUB", "MMF_RED")
        self.cash[ccy] -= excess
        self.inv[ccy] += excess
        account = config.INVESTMENT_ACCOUNT[ccy]
        self._txn(d, config.TRS_MAIN_ACCOUNT[ccy], sub if excess > 0 else red, ccy, -excess, account, position=account)
        self._log(d, "action", "Cash", f"TRS {'invests' if excess > 0 else 'redeems'} {ccy} {abs(excess):,.0f} "
                  f"{'in' if excess > 0 else 'from'} {account}.", reason, None, ccy, excess, account)

    def _interest_items(self, d):
        """One day of interest on today's balances: [(ccy, component, where it accrues, TRS income in ccy)]."""
        items = []
        for ccy in config.CURRENCIES:
            on, basis = self.on.loc[d, ccy], self.basis[ccy]
            items.append((ccy, PNL_MMF, ("inv", ccy), self.inv[ccy] * mmf_rate(on) / basis))
            for (ent, c), bal in list(self.ic.items()):
                if c == ccy and bal:
                    rate = ic_deposit_rate(on) if bal > 0 else ic_loan_rate(on)
                    # + balance = TRS owes the entity: a cost; - balance = the entity owes TRS: income
                    items.append((ccy, PNL_IC_DEPOSIT if bal > 0 else PNL_IC_LOAN, ("ic", (ent, c)),
                                  -bal * rate / basis))
        for pid, p in self.terms.items():
            if p["status"] == "open":
                interest = p["principal"] * p["rate"] / self.basis[p["currency"]]
                deposit = p["position_type"] == "IC_DEPOSIT"
                items.append((p["currency"], PNL_IC_DEPOSIT if deposit else PNL_IC_LOAN, ("term", pid),
                              -interest if deposit else interest))
        items.append(("USD", PNL_IC_DEPOSIT, ("iv", None),
                      -self.iv_dep * ic_deposit_rate(self.on.loc[d, "USD"]) / self.basis["USD"]))
        return items

    def interest_today(self, d, ccy):
        """TRS's net interest income in ccy for one day on today's balances (not booked)."""
        return sum(amount for c, _, _, amount in self._interest_items(d) if c == ccy)

    def _accrue(self, d):
        """Accrue one day of interest; returns {(ccy, component): amount in ccy} (+ = TRS income)."""
        pnl = defaultdict(float)
        for ccy, comp, (kind, key), amount in self._interest_items(d):
            pnl[(ccy, comp)] += amount
            if kind == "inv":
                self.inv_accrued[(ccy, _month_key(d))] += amount
            elif kind == "ic":
                self.ic_accrued[key] -= amount
            elif kind == "term":   # accrued interest the deposit holder (or borrower) is owed (or owes)
                self.terms[key]["accrued"] += -amount if self.terms[key]["position_type"] == "IC_DEPOSIT" else amount
            else:
                self.iv_accrued -= amount
        return pnl

    def _post_ic_interest(self, d, posted):
        by_ccy = defaultdict(float)
        for key, amt in list(self.ic_accrued.items()):
            self.ic[key] += amt
            posted[key] += amt
            by_ccy[key[1]] += amt
            self.ic_accrued[key] = 0.0
        for ccy, amt in sorted(by_ccy.items()):
            if abs(amt) >= 0.5:
                self._log(d, "event", "Interest", f"Month end: net IC interest of {ccy} {amt:+,.0f} is posted to "
                          "the entities' current accounts (+ = TRS pays).", ccy=ccy, amount=amt)
        self._log(d, "event", "Interest", f"Month end: USD {self.iv_accrued:,.0f} interest is added to the IV deposit "
                  f"({IV_DEPOSIT_ID}).", entity="IV", ccy="USD", amount=self.iv_accrued, ref=IV_DEPOSIT_ID)
        self.iv_dep += self.iv_accrued
        self.iv_accrued = 0.0

    # ---------------- records ----------------
    def _balance_sheet(self, ccy):
        """(assets, liabilities) in ccy, before the MTM of FX deals."""
        inv_acc = sum(v for k, v in self.inv_accrued.items() if k[0] == ccy)
        ic_bal = [self.ic[k] + self.ic_accrued[k] for k in self.ic if k[1] == ccy]
        assets = max(self.cash[ccy], 0) + self.inv[ccy] + inv_acc + sum(-b for b in ic_bal if b < 0)
        liabilities = max(-self.cash[ccy], 0) + sum(b for b in ic_bal if b > 0)
        for p in self.terms.values():
            if p["status"] == "open" and p["currency"] == ccy:
                value = p["principal"] + p["accrued"]
                if p["position_type"] == "IC_DEPOSIT":
                    liabilities += value
                else:
                    assets += value
        if ccy == "USD":
            liabilities += self.iv_dep + self.iv_accrued
        return assets, liabilities

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
            self.out["pnl_daily"].append({"pnl_date": d, "currency": ccy, "component": PNL_FX_DEALS,
                                          "amount_ccy": 0.0, "amount_usd": round(self._fx_pnl.get(ccy, 0.0), 2)})
        self._fx_pnl = defaultdict(float)

    def _record(self, d, opening_ic, settled, posted, transfers, opening_cash, mtm):
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
                "interest_posted": round(posted[(ent, ccy)], 2), "transfers": round(transfers[(ent, ccy)], 2),
                "closing": round(self.ic[(ent, ccy)], 2), "accrued_interest": round(self.ic_accrued[(ent, ccy)], 2)})
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
        for pid, p in self.terms.items():
            if p["status"] == "open":
                sign = -1 if p["position_type"] == "IC_DEPOSIT" else 1
                value = sign * (p["principal"] + p["accrued"])
                self.out["valuation"].append({
                    "valuation_date": d, "item_type": "position", "item_id": pid, "currency": p["currency"],
                    "accrued_interest": round(sign * p["accrued"], 2), "mtm": 0.0, "value_ccy": round(value, 2),
                    "value_usd": round(value / fx[p["currency"]], 2)})
        for deal_id, value in sorted(mtm.items()):
            self.out["valuation"].append({"valuation_date": d, "item_type": "fx_deal", "item_id": deal_id,
                                          "currency": "USD", "accrued_interest": 0.0, "mtm": round(value, 2),
                                          "value_ccy": round(value, 2), "value_usd": round(value, 2)})
        for ccy in config.CURRENCIES:
            assets, liabilities = self._balance_sheet(ccy)
            nav_today[ccy] = assets - liabilities
            if ccy == "USD":  # FX deals are valued in USD
                assets += sum(v for v in mtm.values() if v > 0)
                liabilities += sum(-v for v in mtm.values() if v < 0)
            nav = assets - liabilities
            position = 0.0 if ccy == "USD" else self.fx_position(ccy)
            self.out["nav_daily"].append({
                "nav_date": d, "currency": ccy, "assets": round(assets, 2), "liabilities": round(liabilities, 2),
                "nav_ccy": round(nav, 2), "nav_usd": round(nav / fx[ccy], 2),
                "open_fx_position_ccy": round(position, 2), "open_fx_position_usd": round(position / fx[ccy], 2)})
            if self.cash[ccy] < -0.005:
                self.out["alerts"].append({"alert_date": d, "currency": ccy, "alert": "overdraft",
                                           "amount": round(self.cash[ccy], 2)})
            if abs(position / fx[ccy]) > config.FX_TOLERANCE_USD:
                self.out["alerts"].append({"alert_date": d, "currency": ccy, "alert": "fx_outside_tolerance",
                                           "amount": round(position / fx[ccy], 2)})
        self.prev_nav, self.prev_fx = nav_today, fx

    # ---------------- run ----------------
    def run(self):
        self.run_until(self.end)
        return self.results()

    def run_until(self, until):
        """Simulate the days from the next one not yet run up to `until` (inclusive). The engine can stop
        and go on later: the what-if tools stop it on the eve of a day and continue copies of it."""
        d = getattr(self, "next_day", self.start)
        while d <= until:
            self._run_day(d)
            d += timedelta(days=1)
        self.next_day = d

    def clear_outputs(self):
        """Forget the rows recorded so far (the state stays): a continued copy then returns only its new days."""
        self.out = defaultdict(list)

    def _run_day(self, d):
        opening_ic = dict(self.ic)
        opening_cash = {**self.cash, "CHF-DEP": self.inv["CHF"]}
        settled, posted, transfers = defaultdict(float), defaultdict(float), defaultdict(float)
        self._group_flows(d)
        self._zero_balance(d, settled)
        self._settle_fx(d, transfers)
        matured = self._mature_terms(d, transfers)
        self._place_terms(d, matured, transfers)
        for ccy in config.CURRENCIES[1:]:
            self._invest_step(d, ccy)
        self._fx_decisions(d, transfers)   # after investing: the flatten counts today's MMF income
        for ccy in config.CURRENCIES[1:]:
            self._funding_swap(d, ccy, transfers)
        self._invest_step(d, "USD")        # last: swaps move USD
        pnl = self._accrue(d)
        mtm = self._revalue_fx(d)
        if _is_month_end(d):
            self._post_ic_interest(d, posted)
        self._record_pnl(d, pnl)
        self._record(d, opening_ic, settled, posted, transfers, opening_cash, mtm)

    def results(self):
        tables = {name: pd.DataFrame(rows) for name, rows in self.out.items()}
        tables.setdefault("alerts", pd.DataFrame(columns=["alert_date", "currency", "alert", "amount"]))
        tables.setdefault("fx_deal", pd.DataFrame(columns=FX_DEAL_COLUMNS))
        tables.setdefault("activity", pd.DataFrame(columns=ACTIVITY_COLUMNS))
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
        for pid, p in self.terms.items():
            rows.append({"position_id": pid, "position_type": p["position_type"], "counterparty": p["counterparty"],
                         "currency": p["currency"], "principal": round(p["principal"], 2),
                         "rate": round(p["rate"], 6), "start_date": p["start_date"],
                         "maturity_date": p["maturity_date"], "status": p["status"], "facility_id": None,
                         "fund_id": None, "linked_position_id": None})
        return pd.DataFrame(rows)


def run_engine(static, on_rates, fx, start, end, vary=True):
    return Engine(static, on_rates, fx, start, end, vary=vary).run()


def plan_ahead(static, on_rates, fx, start, end, vary=True):
    """The autopilot's plan: what it expects to do on the business days after `end`.

    Runs the engine on past `end` for config.PLAN_BUSINESS_DAYS joint business days, holding the
    last FX and overnight rates, and returns those days' log lines (activity columns plus plan_date,
    the day the plan was made). The scheduled flows are known; rates are not, so the real actions
    can differ when rates move. The group flows due on those days come first, as the cause of
    most of the actions.
    """
    plan_end = add_joint_business_days(end, config.PLAN_BUSINESS_DAYS, config.CURRENCIES)
    days = pd.date_range(end + timedelta(days=1), plan_end).date
    hold = lambda df: pd.concat([df.loc[:end], pd.DataFrame([df.loc[end]] * len(days), index=days)])  # noqa: E731
    eng = Engine(static, hold(on_rates), hold(fx), start, plan_end, vary=vary)
    log = eng.run()["activity"]
    names = static["flow_codes"].set_index("flow_code")["description"]
    flows = eng.flows[(eng.flows["value_date"] > end) & (eng.flows["value_date"] <= plan_end)]
    due = pd.DataFrame([{
        "activity_date": f.value_date, "seq": 0, "kind": "event", "category": "Group flows",
        "entity_code": f.entity_code, "currency": f.currency, "amount": round(f.amount, 2), "ref": f.schedule_id,
        "description": f"{f.entity_code} {'receives' if f.amount > 0 else 'pays'} {f.currency} {abs(f.amount):,.0f}: "
                       f"{names[f.flow_code][0].lower() + names[f.flow_code][1:]}.", "reason": None}
        for f in flows.itertuples()], columns=ACTIVITY_COLUMNS)
    plan = pd.concat([due, log[log["activity_date"] > end]], ignore_index=True)
    plan = plan.sort_values("activity_date", kind="stable").reset_index(drop=True)
    plan["seq"] = plan.groupby("activity_date").cumcount() + 1
    plan.insert(0, "plan_date", end)
    return plan
