import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import daily_fx_rates as fx  # noqa: E402


def test_chf_is_a_target_currency():
    assert fx.TARGET_CURRENCIES == ["USD", "EUR", "GBP", "CHF"]
    assert fx.QUOTED_CURRENCIES == ["EUR", "GBP", "CHF"]


def test_rows_from_api_adds_usd_and_every_quoted_currency():
    rates = {
        "2026-10-16": {"EUR": 0.857, "GBP": 0.745, "CHF": 0.795},
        "2026-10-19": {"EUR": 0.858, "GBP": 0.746, "CHF": 0.796},
    }
    rows = pd.DataFrame(fx._rows_from_api(rates))
    assert len(rows) == 8
    assert set(rows["currency"]) == {"USD", "EUR", "GBP", "CHF"}
    assert (rows.loc[rows["currency"] == "USD", "fx_to_usd"] == 1.0).all()
    chf = rows[(rows["currency"] == "CHF") & (rows["date"] == "2026-10-19")]["fx_to_usd"].item()
    assert chf == 0.796


def test_normalize_keeps_chf_rows():
    df = pd.DataFrame([
        {"date": "2026-10-19", "currency": "chf", "fx_to_usd": 0.796, "fx_quality_flag": "raw"},
        {"date": "2026-10-19", "currency": "JPY", "fx_to_usd": 150.0, "fx_quality_flag": "raw"},
    ])
    out = fx._normalize_fx_frame(df)
    assert list(out["currency"]) == ["CHF"]


def test_history_starts_on_1_jan_2025():
    assert fx.HISTORY_START_DATE.isoformat() == "2025-01-01"


def _rates(rows):
    """rows: (date, currency, fx_to_usd, flag) -> fx_rates frame."""
    return pd.DataFrame(rows, columns=["date", "currency", "fx_to_usd", "fx_quality_flag"])


def _value(grid, day, currency, column="fx_to_usd"):
    return grid.loc[(grid["date"] == date.fromisoformat(day)) & (grid["currency"] == currency), column].item()


def _market_week():
    """EUR, GBP and CHF on Thursday 15 and Friday 16 October 2026, plus Monday 19."""
    rows = []
    for day, eur, gbp, chf in [
        ("2026-10-15", 0.856, 0.744, 0.794),
        ("2026-10-16", 0.857, 0.745, 0.795),
        ("2026-10-19", 0.858, 0.746, 0.796),
    ]:
        rows += [(day, "EUR", eur, "raw"), (day, "GBP", gbp, "raw"), (day, "CHF", chf, "raw")]
    return _rates(rows)


def test_grid_fills_weekend_from_friday_and_flags_it():
    grid = fx.build_daily_grid(_market_week(), date(2026, 10, 15), date(2026, 10, 19))
    assert len(grid) == 5 * 4
    assert _value(grid, "2026-10-17", "EUR") == 0.857
    assert _value(grid, "2026-10-18", "GBP") == 0.745
    assert _value(grid, "2026-10-17", "EUR", "fx_quality_flag") == "filled"
    assert _value(grid, "2026-10-16", "EUR", "fx_quality_flag") == "raw"
    assert _value(grid, "2026-10-17", "USD") == 1.0
    assert _value(grid, "2026-10-17", "USD", "fx_quality_flag") == "raw"


def test_grid_never_fills_one_currency_from_another():
    rates = _market_week()
    rates = rates[rates["currency"] != "CHF"]
    grid = fx.build_daily_grid(rates, date(2026, 10, 15), date(2026, 10, 19))
    assert grid.loc[grid["currency"] == "CHF", "fx_to_usd"].isna().all()


def test_grid_carries_a_rate_from_before_the_start_into_it():
    # 1 Jan is an ECB holiday: the API answers with 31 Dec, which fills 1 Jan
    # and is then dropped from the output.
    rates = _rates([
        ("2025-12-31", "EUR", 0.851, "raw"),
        ("2026-01-02", "EUR", 0.853, "raw"),
    ])
    grid = fx.build_daily_grid(rates, date(2026, 1, 1), date(2026, 1, 2))
    assert grid["date"].min() == date(2026, 1, 1)
    assert _value(grid, "2026-01-01", "EUR") == 0.851
    assert _value(grid, "2026-01-01", "EUR", "fx_quality_flag") == "filled"


def test_grid_fills_back_only_when_nothing_comes_before():
    rates = _rates([("2026-01-02", "EUR", 0.853, "raw")])
    grid = fx.build_daily_grid(rates, date(2026, 1, 1), date(2026, 1, 2))
    assert _value(grid, "2026-01-01", "EUR") == 0.853
    assert _value(grid, "2026-01-01", "EUR", "fx_quality_flag") == "filled"


def test_daily_run_refills_weekend_after_a_late_correction():
    stored = fx._normalize_fx_frame(fx.build_daily_grid(_market_week(), date(2026, 10, 15), date(2026, 10, 19)))
    corrected_friday = fx._normalize_fx_frame(_rates([("2026-10-16", "EUR", 0.860, "raw")]))
    inputs = fx.daily_window_inputs(stored, corrected_friday, date(2026, 10, 15))
    grid = fx.build_daily_grid(inputs, date(2026, 10, 15), date(2026, 10, 19))
    assert _value(grid, "2026-10-16", "EUR") == 0.860
    assert _value(grid, "2026-10-17", "EUR") == 0.860
    assert _value(grid, "2026-10-18", "EUR") == 0.860
    assert _value(grid, "2026-10-18", "EUR", "fx_quality_flag") == "filled"


def test_daily_run_keeps_a_filled_first_day_as_the_anchor():
    # The window starts on Saturday, a filled day carried from Friday.
    stored = fx._normalize_fx_frame(_rates([
        ("2026-10-17", "EUR", 0.857, "filled"),
        ("2026-10-18", "EUR", 0.857, "filled"),
        ("2026-10-19", "EUR", 0.858, "raw"),
    ]))
    inputs = fx.daily_window_inputs(stored, fx._empty_fx_frame(), date(2026, 10, 17))
    grid = fx.build_daily_grid(inputs, date(2026, 10, 17), date(2026, 10, 19))
    assert _value(grid, "2026-10-17", "EUR") == 0.857
    assert _value(grid, "2026-10-17", "EUR", "fx_quality_flag") == "filled"
    assert _value(grid, "2026-10-18", "EUR") == 0.857


def test_full_check_stops_when_the_api_returns_too_little_history():
    week = fx._normalize_fx_frame(_market_week())
    fx.check_api_coverage(week, date(2026, 10, 15), date(2026, 10, 19))
    with pytest.raises(RuntimeError, match="refusing to rebuild"):
        fx.check_api_coverage(week, date(2026, 10, 1), date(2026, 10, 19))
