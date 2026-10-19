import sys
from pathlib import Path

import pandas as pd

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
