"""Smoke test: every app page runs without an exception (Streamlit AppTest)."""

import sys
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP_DIR = Path(__file__).resolve().parents[1] / "app"
PAGES = sorted(p.name for p in (APP_DIR / "pages").glob("*.py"))


@pytest.fixture(autouse=True)
def app_on_path(monkeypatch):
    monkeypatch.syspath_prepend(str(APP_DIR))
    monkeypatch.chdir(APP_DIR)


def test_main_app_runs():
    at = st_testing.AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30).run()
    assert not at.exception


@pytest.mark.parametrize("page", PAGES)
def test_each_page_runs(page):
    at = st_testing.AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30).run()
    at.switch_page(f"pages/{page}").run()
    assert not at.exception, page
