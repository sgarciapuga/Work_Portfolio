"""App pages with a simulated history (synthetic flat rates, written to a temp folder)."""

from datetime import date

import pandas as pd
import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

from tsim import config  # noqa: E402
from tsim.engine import run_engine  # noqa: E402
from tsim.static_data import load_static  # noqa: E402

from test_app import APP_DIR  # noqa: E402


@pytest.fixture(scope="module")
def history_dir(tmp_path_factory):
    start, end = config.HISTORY_START, date(2025, 3, 31)
    days = pd.date_range(start, end).date
    fx = pd.DataFrame({"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "CHF": 0.90}, index=days)
    on = pd.DataFrame({"USD": 0.043, "EUR": 0.029, "GBP": 0.047, "CHF": 0.005}, index=days)
    out = tmp_path_factory.mktemp("tsim_data")
    for name, df in run_engine(load_static(), on, fx, start, end).items():
        df.to_csv(out / f"{name}.csv", index=False)
    rates = on.stack().rename("rate").reset_index().rename(columns={"level_0": "rate_date", "level_1": "currency"})
    rates["tenor"], rates["source"] = "ON", "test"
    rates.to_csv(out / "ir_rates.csv", index=False)
    return out


@pytest.mark.parametrize("page", ["pages/overview.py", "pages/balance_sheet.py", "pages/market_data.py",
                                  "pages/positions.py"])
def test_pages_with_history(page, history_dir, monkeypatch):
    monkeypatch.setenv("TSIM_DATA_DIR", str(history_dir))
    monkeypatch.setenv("TSIM_NO_DB", "1")
    monkeypatch.syspath_prepend(str(APP_DIR))
    monkeypatch.chdir(APP_DIR)
    import streamlit as st

    st.cache_data.clear()  # an earlier test may have cached "no history"
    at = st_testing.AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=60).run()
    at.switch_page(page).run()
    assert not at.exception, at.exception
    if page.endswith("overview.py"):
        labels = [m.label for m in at.metric]
        assert "TRS NAV (USD)" in labels
        nav = [m.value for m in at.metric if m.label == "TRS NAV (USD)"][0]
        assert nav.startswith("USD 20")
