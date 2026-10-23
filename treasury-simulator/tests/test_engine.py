from datetime import date

import pandas as pd
import pytest

from tsim import config
from tsim.engine import IV_DEPOSIT_ID, fx_daily, run_engine
from tsim.static_data import load_static

START, END = date(2025, 1, 1), date(2025, 6, 30)
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "CHF": 0.90}
ON = {"USD": 0.043, "EUR": 0.029, "GBP": 0.047, "CHF": 0.005}


def _flat(values):
    days = pd.date_range(START, END, freq="D").date
    return pd.DataFrame({c: [v] * len(days) for c, v in values.items()}, index=days)[config.CURRENCIES]


@pytest.fixture(scope="module")
def result():
    return run_engine(load_static(), _flat(ON), _flat(FX), START, END)


def test_entity_accounts_are_zero_every_day(result):
    bal = result["cash_balance"]
    entity = bal[~bal["account_id"].str.startswith("TRS")]
    assert (entity["closing"].abs() < 0.01).all()


def test_settlements_mirror_group_flows(result):
    txn = result["cash_txn"]
    codes = load_static()["flow_codes"]
    flows = txn[txn["flow_code"].isin(codes.loc[codes["category"] == "group_flows", "flow_code"])]
    trs_settle = txn[(txn["flow_code"] == "IHB_SETTLE") & txn["account_id"].str.startswith("TRS")]
    for ccy in config.CURRENCIES:
        assert flows.loc[flows["currency"] == ccy, "amount"].sum() == pytest.approx(
            trs_settle.loc[trs_settle["currency"] == ccy, "amount"].sum(), abs=0.05)


def test_opening_nav_is_trs_equity_and_other_currencies_are_flat(result):
    nav = result["nav_daily"]
    first = nav[nav["nav_date"] == START].set_index("currency")
    assert first.loc["USD", "nav_ccy"] == pytest.approx(config.TRS_EQUITY_USD, rel=1e-3)
    last = nav[nav["nav_date"] == END].set_index("currency")
    for ccy in ["EUR", "GBP", "CHF"]:
        # only the small interest margin builds up in non-USD currencies
        assert abs(last.loc[ccy, "open_fx_position_usd"]) < config.FX_TOLERANCE_USD


def test_trs_keeps_operating_minimum_and_no_overdraft(result):
    assert result["alerts"].empty
    trs = result["cash_balance"]
    main = trs[trs["account_id"].isin(config.TRS_MAIN_ACCOUNT.values())]
    usd = main[main["account_id"] == "TRS-BKA-USD"]["closing"]
    assert (usd < config.OPERATING_MIN_USD + config.MIN_INVESTMENT_TRADE_USD + 1).all()


def test_mmf_interest_paid_on_bd2_and_matches_accrual(result):
    txn = result["cash_txn"]
    usd_int = txn[(txn["flow_code"] == "MMF_INT") & (txn["currency"] == "USD")]
    assert date(2025, 2, 4) in set(usd_int["value_date"])        # BD2 of Feb 2025 (USD)
    jan = usd_int[usd_int["value_date"] == date(2025, 2, 4)]["amount"].item()
    # about USD 105m x (4.3% - 5 bp) x 31/360; the US fee received on 10 Jan adds a little
    assert jan == pytest.approx(105e6 * (0.043 - 0.0005) * 31 / 360, rel=0.05)


def test_iv_deposit_earns_mmf_minus_10bp(result):
    val = result["valuation"]
    iv = val[(val["item_id"] == IV_DEPOSIT_ID) & (val["valuation_date"] == date(2025, 2, 1))]["value_ccy"].item()
    rate = 0.043 - 0.0005 - 0.0010
    capitalised = 80e6 * (1 + rate * 31 / 360)          # January interest posted on 31 Jan
    expected = capitalised * (1 + rate / 360)           # plus 1 Feb accrued
    assert -iv == pytest.approx(expected, rel=1e-6)


def test_run_is_deterministic():
    a = run_engine(load_static(), _flat(ON), _flat(FX), START, date(2025, 2, 28))
    b = run_engine(load_static(), _flat(ON), _flat(FX), START, date(2025, 2, 28))
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_fx_daily_fills_gaps():
    rows = pd.DataFrame([{"date": "2025-01-02", "currency": c, "fx_to_usd": v} for c, v in FX.items()])
    fx = fx_daily(rows, date(2025, 1, 1), date(2025, 1, 5))
    assert fx.loc[date(2025, 1, 5), "GBP"] == 0.79


def test_pnl_parts_add_up_to_nav_change():
    # FX moves on 1 Feb, so FX revaluation must show up too
    fx = _flat(FX)
    fx.loc[date(2025, 2, 1):, "GBP"] = 0.75
    res = run_engine(load_static(), _flat(ON), fx, START, date(2025, 3, 31))
    nav = res["nav_daily"].groupby("nav_date")["nav_usd"].sum()
    pnl = res["pnl_daily"].groupby("pnl_date")["amount_usd"].sum()
    change = nav.diff().dropna()
    assert (change - pnl.loc[change.index]).abs().max() < 1.0      # rounding only
    fx_reval = res["pnl_daily"].query("component == 'FX revaluation'")
    assert abs(fx_reval[fx_reval["pnl_date"] == date(2025, 2, 1)]["amount_usd"].sum()) > 0
