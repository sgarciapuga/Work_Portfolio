import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sweep_engine import sweep_cash  # noqa: E402


def _balances(rows):
    """rows: (account_number, currency, closing_balance) -> one day's balances."""
    df = pd.DataFrame(rows, columns=["account_number", "currency", "closing_balance"])
    df["date"] = "2026-10-21"
    return df


def _closing(df):
    return dict(zip(df["account_number"], df["closing_balance"]))


def test_a_surplus_is_never_swept_twice():
    # 21 Oct 2026 in GBP: JPM's deficit took all of Santander's surplus, then
    # HSBC's deficit took it again and left Santander overdrawn.
    daily = _balances([
        ("jpm", "GBP", -123066.40),
        ("hsbc", "GBP", -7256.38),
        ("santander", "GBP", 36821.18),
        ("citi", "GBP", 5381.34),
    ])
    out, sweeps = sweep_cash(daily)
    closing = _closing(out)
    assert closing["santander"] == pytest.approx(0)
    assert closing["citi"] == pytest.approx(0)
    assert closing["jpm"] == pytest.approx(-123066.40 + 36821.18 + 5381.34)
    assert closing["hsbc"] == pytest.approx(-7256.38)
    assert sweeps["amount"].sum() == pytest.approx(0)


def test_one_surplus_covers_several_deficits_while_it_lasts():
    daily = _balances([("a", "EUR", -30.0), ("b", "EUR", -20.0), ("c", "EUR", 100.0)])
    out, sweeps = sweep_cash(daily)
    assert _closing(out) == pytest.approx({"a": 0.0, "b": 0.0, "c": 50.0})
    assert len(sweeps) == 4


def test_sweeps_stay_within_a_currency():
    daily = _balances([("usd_short", "USD", -50.0), ("eur_long", "EUR", 500.0)])
    out, sweeps = sweep_cash(daily)
    assert _closing(out) == {"usd_short": -50.0, "eur_long": 500.0}
    assert sweeps.empty


def test_total_cash_per_currency_is_unchanged():
    daily = _balances([
        ("a", "USD", -80.0), ("b", "USD", 60.0), ("c", "USD", 40.0),
        ("d", "GBP", -10.0), ("e", "GBP", 5.0),
    ])
    before = daily.groupby("currency")["closing_balance"].sum()
    out, _ = sweep_cash(daily.copy())
    after = out.groupby("currency")["closing_balance"].sum()
    pd.testing.assert_series_equal(before, after)
    assert (out.loc[out["account_number"].isin(["b", "c", "e"]), "closing_balance"] >= 0).all()
