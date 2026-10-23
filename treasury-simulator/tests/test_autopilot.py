"""Phase 3 autopilot: FX orders and cover, flattening, swaps, IC term deposits, MTM."""

from datetime import date

import pandas as pd
import pytest

from tsim import config
from tsim.calendars import add_joint_business_days, add_months
from tsim.engine import run_engine
from tsim.market import deal_rate
from tsim.static_data import load_static

START, END = date(2025, 1, 1), date(2025, 6, 30)
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "CHF": 0.90}
ON = {"USD": 0.043, "EUR": 0.029, "GBP": 0.047, "CHF": 0.005}


def _flat(values, end=END):
    days = pd.date_range(START, end, freq="D").date
    return pd.DataFrame({c: [v] * len(days) for c, v in values.items()}, index=days)[config.CURRENCIES]


@pytest.fixture(scope="module")
def result():
    return run_engine(load_static(), _flat(ON), _flat(FX), START, END)


# ---------------- FX orders and cover ----------------
def test_month_end_conversions_are_booked_ahead_and_covered_net(result):
    deals = result["fx_deal"]
    jan = deals[deals["trade_date"] == date(2025, 1, 24)]          # 5 joint business days before 31 Jan
    internal, external = jan[jan["is_internal"]], jan[~jan["is_internal"]]
    assert set(internal["counterparty"]) == {"US", "CH"}           # they pay MGT's recharge in GBP
    assert (jan["value_date"] == date(2025, 1, 31)).all()          # last joint business day of January
    assert internal["sell_amount"][internal["sell_ccy"] == "GBP"].sum() == pytest.approx(370_000)
    gbp = external[external["buy_ccy"] == "GBP"]
    assert len(gbp) == 1 and gbp["buy_amount"].item() == pytest.approx(370_000)   # one net cover deal
    chf = external[external["sell_ccy"] == "CHF"]                   # CH paid TRS in CHF: TRS sells it
    assert chf["sell_amount"].item() == pytest.approx(internal.loc[internal["counterparty"] == "CH", "buy_amount"].item())


def test_entities_hold_no_foreign_currency_after_month_end(result):
    ic = result["ic_current_account"]
    own = {"MGT": "GBP", "US": "USD", "CH": "CHF", "EU": "EUR"}
    foreign = ic[ic.apply(lambda r: r["entity_code"] in own and r["currency"] != own[r["entity_code"]], axis=1)]
    month_ends = [date(2025, m, d) for m, d in [(1, 31), (2, 28), (3, 31), (4, 30), (5, 30), (6, 30)]]
    assert (foreign[foreign["balance_date"].isin(month_ends)]["closing"].abs() < 1).all()


def test_ic_current_account_moves_add_up(result):
    ic = result["ic_current_account"]
    diff = ic["opening"] + ic["settlements"] + ic["interest_posted"] + ic["transfers"] - ic["closing"]
    assert diff.abs().max() < 0.05


def test_deal_rate_is_in_market_convention():
    assert deal_rate("GBP", 100, "USD", 126.58) == pytest.approx(1.2658)    # GBP/USD: USD per GBP
    assert deal_rate("USD", 100, "CHF", 90) == pytest.approx(0.90)          # USD/CHF: CHF per USD
    assert deal_rate("CHF", 112, "GBP", 100) == pytest.approx(1.12)         # GBP/CHF: CHF per GBP


# ---------------- MTM ----------------
def test_mtm_is_zero_when_booked_and_back_to_back_deals_cancel():
    fx = _flat(FX, date(2025, 2, 10))
    fx.loc[date(2025, 1, 28):, "GBP"] = 0.75                      # GBP strengthens while the forwards are open
    res = run_engine(load_static(), _flat(ON, date(2025, 2, 10)), fx, START, date(2025, 2, 10))
    val = res["valuation"][res["valuation"]["item_type"] == "fx_deal"]
    booked = val[val["valuation_date"] == date(2025, 1, 24)]
    assert booked["mtm"].abs().max() < 0.05
    moved = val[val["valuation_date"] == date(2025, 1, 28)].set_index("item_id")["mtm"]
    deals = res["fx_deal"].set_index("deal_id")
    cover = deals[(~deals["is_internal"]) & (deals["buy_ccy"] == "GBP")].index[0]
    assert moved[cover] == pytest.approx(370_000 * (1 / 0.75 - 1 / 0.79), rel=1e-3)   # TRS bought GBP: a gain
    assert abs(moved.sum()) < 1.0                                  # the internal deals lose the same
    nav = res["nav_daily"].groupby("nav_date")["nav_usd"].sum()
    pnl = res["pnl_daily"].groupby("pnl_date")["amount_usd"].sum()
    assert (nav.diff().dropna() - pnl.loc[nav.index[1:]]).abs().max() < 1.0


# ---------------- flattening ----------------
def test_flatten_with_spot_t_plus_2_keeps_the_position_inside_the_tolerance(monkeypatch):
    monkeypatch.setattr(config, "FX_TOLERANCE_USD", 2_000)        # small enough for the interest margin to cross
    res = run_engine(load_static(), _flat(ON), _flat(FX), START, END)
    spot = res["fx_deal"][res["fx_deal"]["deal_type"] == "spot"]
    assert len(spot) > 0
    for r in spot.itertuples():
        ccy = r.buy_ccy if r.buy_ccy != "USD" else r.sell_ccy
        assert r.value_date == add_joint_business_days(r.trade_date, config.SPOT_DAYS, [ccy, "USD"])
    nav = res["nav_daily"]
    assert nav["open_fx_position_usd"].abs().max() <= 2_000 + 500   # flat after each deal, plus a day's interest


# ---------------- swaps ----------------
def test_currency_short_of_cash_is_funded_with_a_swap():
    static = load_static()
    big_payment = {"schedule_id": "TEST", "entity_code": "CH", "flow_code": "TAX", "currency": "CHF",
                   "amount": -30_000_000, "frequency": "annual", "day_rule": "03-03",
                   "counterparty": "Tax authority", "counterparty_entity": None}
    static["fee_schedule"] = pd.concat([static["fee_schedule"], pd.DataFrame([big_payment])], ignore_index=True)
    res = run_engine(static, _flat(ON), _flat(FX), START, END)
    swaps = res["fx_deal"][res["fx_deal"]["deal_type"] == "swap"]
    trade = swaps["trade_date"].min()
    # the look-ahead sees the payment coming and funds it on or before the day
    assert add_joint_business_days(trade, config.LOOKAHEAD_BUSINESS_DAYS, ["CHF", "USD"]) >= date(2025, 3, 3) >= trade
    first = swaps[swaps["trade_date"] == trade].set_index("leg")
    assert first.loc["near", "value_date"] == trade and first.loc["near", "buy_ccy"] == "CHF"
    assert first.loc["far", "value_date"] == add_months(trade, config.SWAP_TENOR_MONTHS, ["CHF", "USD"])
    assert first.loc["far", "sell_amount"] == first.loc["near", "buy_amount"]       # same CHF back at maturity
    assert res["alerts"].empty                                                       # no overdraft, still flat


# ---------------- IC term deposits ----------------
def test_ic_deposits_placed_at_a_fixed_rate_and_paid_at_maturity(result):
    pos = result["position"].set_index("position_id")
    dep = pos.loc["ICD-MGT-GBP-20250102"]
    rate = ON["GBP"] + (config.MMF_SPREAD_BP + config.IC_DEPOSIT_MARGIN_BP + config.IC_TERM_PREMIUM_BP) / 10_000
    assert dep["rate"] == pytest.approx(rate)
    assert dep["maturity_date"] == date(2025, 4, 2)
    val = result["valuation"]
    accrued = val[(val["item_id"] == dep.name) & (val["valuation_date"] == date(2025, 4, 1))]["accrued_interest"].item()
    assert -accrued == pytest.approx(dep["principal"] * rate * 90 / 365, abs=0.05)   # 2 Jan to 1 Apr
    assert dep.name not in set(val[val["valuation_date"] == date(2025, 4, 2)]["item_id"])   # gone at maturity


def test_deposits_never_leave_an_entity_short_on_call(result):
    ic = result["ic_current_account"]
    for ent, ccy in {"MGT": "GBP", "CH": "CHF", "EU": "EUR"}.items():
        assert (ic[(ic["entity_code"] == ent) & (ic["currency"] == ccy)]["closing"] >= 0).all(), ent


def test_ladder_has_a_deposit_maturing_most_months(result):
    pos = result["position"]
    mgt = pos[pos["position_id"].str.startswith("ICD-MGT")]
    assert mgt["maturity_date"].map(lambda d: (d.year, d.month)).nunique() >= 3
