from datetime import date

import pandas as pd
import pytest

from tsim.market import differentials_bp, forward_points_history, forward_rate, implied_forwards, market_quotes

FX_ROWS = pd.DataFrame([
    {"date": "2025-01-02", "currency": "EUR", "fx_to_usd": 0.8, "fx_quality_flag": "raw"},
    {"date": "2025-01-02", "currency": "GBP", "fx_to_usd": 0.625, "fx_quality_flag": "raw"},
    {"date": "2025-01-02", "currency": "CHF", "fx_to_usd": 0.9, "fx_quality_flag": "raw"},
    {"date": "2025-01-02", "currency": "USD", "fx_to_usd": 1.0, "fx_quality_flag": "raw"},
    {"date": "2025-01-04", "currency": "EUR", "fx_to_usd": 0.8, "fx_quality_flag": "filled"},
    {"date": "2025-01-04", "currency": "GBP", "fx_to_usd": 0.625, "fx_quality_flag": "filled"},
    {"date": "2025-01-04", "currency": "CHF", "fx_to_usd": 0.9, "fx_quality_flag": "filled"},
])
ON = pd.DataFrame({"USD": [0.04, 0.04], "EUR": [0.02, 0.02], "GBP": [0.04, 0.04], "CHF": [0.0, 0.0]},
                  index=[date(2025, 1, 2), date(2025, 1, 4)])


def test_market_convention():
    q = market_quotes(FX_ROWS)
    assert q.loc[date(2025, 1, 2), "EUR/USD"] == pytest.approx(1.25)
    assert q.loc[date(2025, 1, 2), "GBP/USD"] == pytest.approx(1.6)
    assert q.loc[date(2025, 1, 2), "USD/CHF"] == pytest.approx(0.9)
    assert list(q["is_raw"]) == [True, False]


def test_forward_points_follow_the_rate_differential():
    # USD rates above EUR: EUR/USD forward above spot (positive points)
    assert forward_rate(1.25, 0.02, 0.04, 91, 360, 360) > 1.25
    fwd = implied_forwards(market_quotes(FX_ROWS), ON, date(2025, 1, 2)).set_index("pair")
    # EUR/USD 3M: 1.25 x (1 + 0.04 x 91/360) / (1 + 0.02 x 91/360) = 1.256285...
    assert fwd.loc["EUR/USD", "fwd_3M"] == pytest.approx(1.25 * (1 + 0.04 * 91 / 360) / (1 + 0.02 * 91 / 360))
    assert fwd.loc["EUR/USD", "points_3M"] > 0
    assert fwd.loc["USD/CHF", "points_3M"] < 0          # CHF rates below USD: USD/CHF points negative
    # GBP and USD both 4%, but GBP is actual/365 and USD actual/360: small positive points
    assert 0 < fwd.loc["GBP/USD", "points_1M"] < 10


def test_history_and_differentials():
    hist = forward_points_history(market_quotes(FX_ROWS), ON, "3M")
    assert len(hist) == 2
    diff = differentials_bp(ON)
    assert diff.loc[date(2025, 1, 2), "EUR"] == pytest.approx(-200)
