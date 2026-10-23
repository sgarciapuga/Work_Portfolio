"""Phase 3b: play one day yourself and compare with the autopilot."""

from datetime import date

import pandas as pd
import pytest

from tsim import config
from tsim.engine import run_engine
from tsim.static_data import load_static
from tsim.whatif import compare, play, proposals, setup, your_day

START, END = date(2025, 1, 1), date(2025, 2, 28)
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "CHF": 0.90}
ON = {"USD": 0.043, "EUR": 0.029, "GBP": 0.047, "CHF": 0.005}
HEDGE_DAY = date(2025, 1, 24)     # month-end forwards booked
FEE_DAY = date(2025, 1, 10)       # quarterly management fees received


def _flat(values):
    days = pd.date_range(START, END, freq="D").date
    return pd.DataFrame({c: [v] * len(days) for c, v in values.items()}, index=days)[config.CURRENCIES]


@pytest.fixture(scope="module")
def hedge_base():
    return setup(load_static(), _flat(ON), _flat(FX), START, HEDGE_DAY, END)


def test_playing_the_autopilot_gives_the_normal_history(hedge_base):
    full = run_engine(load_static(), _flat(ON), _flat(FX), START, END)
    auto = play(hedge_base, HEDGE_DAY, END)
    for name, col in [("nav_daily", "nav_date"), ("activity", "activity_date"), ("cash_txn", "value_date")]:
        expected = full[name][full[name][col] >= HEDGE_DAY].reset_index(drop=True)
        cols = [c for c in expected.columns if c != "txn_id"]   # transaction numbers restart in a copy
        pd.testing.assert_frame_equal(auto[name][cols].reset_index(drop=True), expected[cols], check_dtype=False)


def test_proposals_list_the_days_decisions(hedge_base):
    props, day = proposals(hedge_base, HEDGE_DAY)
    p = props.set_index("key")
    assert p.loc["cover|GBP|2025-01-31", "proposed"] == pytest.approx(370_000)
    assert p.loc["cover|CHF|2025-01-31", "proposed"] < 0                      # TRS sells the CHF it received
    assert {f"extra_spot|{c}" for c in ["EUR", "GBP", "CHF"]} <= set(p.index)
    assert (day["activity"]["activity_date"] == HEDGE_DAY).all()


def test_leaving_the_month_end_unhedged_shows_as_risk(hedge_base):
    props, _ = proposals(hedge_base, HEDGE_DAY)
    auto = play(hedge_base, HEDGE_DAY, END)
    mine = play(hedge_base, HEDGE_DAY, END, your_day(props, **{"cover|GBP|2025-01-31": 0}))
    table = compare(auto, mine, _flat(FX), HEDGE_DAY).set_index("Measure")
    assert table.loc["Days outside FX tolerance", "Yours"] > table.loc["Days outside FX tolerance", "Autopilot"] == 0
    assert table.loc["Loss if FX moves 2% against TRS (USD)", "Difference"] > 5_000   # GBP 370k short x 2%
    deals = mine["fx_deal"]
    spots = deals[deals["deal_type"] == "spot"]
    assert not (spots["trade_date"] == HEDGE_DAY).any()      # your day: no spot you did not decide
    assert (spots["trade_date"] > HEDGE_DAY).any()           # the autopilot flattens on the next business day


def test_not_investing_the_fees_costs_interest():
    base = setup(load_static(), _flat(ON), _flat(FX), START, FEE_DAY, END)
    props, _ = proposals(base, FEE_DAY)
    assert props.set_index("key").loc["invest|GBP", "proposed"] > 5_000_000          # MGT's GBP 7.5m fee
    auto = play(base, FEE_DAY, END)
    mine = play(base, FEE_DAY, END, your_day(props, **{"invest|GBP": 0}))
    table = compare(auto, mine, _flat(FX), FEE_DAY).set_index("Measure")
    assert table.loc["of which interest (USD)", "Difference"] < 0                     # a day of MMF interest lost
    assert table.loc["Average idle cash (USD)", "Difference"] > 0


def test_your_own_spot_deal_is_booked(hedge_base):
    props, _ = proposals(hedge_base, HEDGE_DAY)
    mine = play(hedge_base, HEDGE_DAY, END, your_day(props, **{"extra_spot|EUR": 1_000_000}))
    log = mine["activity"]
    assert log["reason"].eq("Your own spot deal.").any()
    deal = mine["fx_deal"][(mine["fx_deal"]["trade_date"] == HEDGE_DAY) & (mine["fx_deal"]["deal_type"] == "spot")]
    assert deal["buy_amount"].tolist() == [1_000_000] and deal["buy_ccy"].tolist() == ["EUR"]
