"""Overnight risk-free rates from the central banks (free, no API key).

USD SOFR (New York Fed), EUR ESTR (ECB), GBP SONIA (Bank of England),
CHF SARON (SNB data portal). Rates are stored as decimals (0.043 = 4.3%).

Each fetch_* function downloads; each parse_* function only reads the text, so
the parsing is tested without network. If a source changes its format, the
parser raises a clear error and the daily workflow fails (turns red).
"""

import io
import time
from datetime import date, timedelta

import pandas as pd
import requests

from tsim import config

RATE_COLUMNS = ["rate_date", "currency", "tenor", "rate", "source"]
HEADERS = {"User-Agent": "Mozilla/5.0 (treasury-simulator portfolio project)"}
TIMEOUT = 60
# Seconds to wait before the 2nd and 3rd attempts when a server fails for a moment.
RETRY_WAITS = (10, 30)

SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
ESTR_URL = "https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT"
SONIA_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
SARON_URL = "https://data.snb.ch/api/cube/{cube}/data/csv/en"
SARON_CUBE = "snbgwdzid"      # SNB: official interest rates and SARON, daily
SARON_SERIES = "SARON"


def _frame(dates, values, currency, source):
    df = pd.DataFrame({"rate_date": [d.date() for d in pd.to_datetime(pd.Series(list(dates)))],
                       "rate": pd.to_numeric(pd.Series(list(values)), errors="coerce") / 100})
    df = df.dropna().drop_duplicates("rate_date", keep="last")
    if df.empty:
        raise ValueError(f"{source}: no rates found in the response")
    df["currency"], df["tenor"], df["source"] = currency, "ON", source
    return df[RATE_COLUMNS].sort_values("rate_date").reset_index(drop=True)


# ---------------- parsers ----------------
def parse_sofr(payload):
    rows = [r for r in payload.get("refRates", []) if r.get("type", "SOFR") == "SOFR"]
    return _frame([r["effectiveDate"] for r in rows], [r["percentRate"] for r in rows], "USD", "SOFR")


def parse_estr(text):
    df = pd.read_csv(io.StringIO(text))
    if not {"TIME_PERIOD", "OBS_VALUE"} <= set(df.columns):
        raise ValueError("ESTR: expected TIME_PERIOD and OBS_VALUE columns")
    return _frame(df["TIME_PERIOD"], df["OBS_VALUE"], "EUR", "ESTR")


def parse_sonia(text):
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().upper() for c in df.columns]
    if not {"DATE", "IUDSOIA"} <= set(df.columns):
        raise ValueError("SONIA: expected DATE and IUDSOIA columns")
    return _frame(pd.to_datetime(df["DATE"], format="%d %b %Y"), df["IUDSOIA"], "GBP", "SONIA")


def parse_saron(text, series=SARON_SERIES):
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.replace('"', "").startswith("Date;")), None)
    if start is None:
        raise ValueError("SARON: no 'Date;' header line in the SNB response")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])), sep=";")
    if "D0" in df.columns:
        df = df[df["D0"].astype(str).str.upper() == series.upper()]
    return _frame(df["Date"], df["Value"], "CHF", "SARON")


# ---------------- downloads ----------------
def _get(url, params):
    """GET that retries temporary failures: server errors (5xx), timeouts, dropped connections.

    Any other HTTP error (a 4xx, such as a moved URL) fails at once, as does a
    parsing error after a successful download.
    """
    for wait in (*RETRY_WAITS, None):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code < 500:
                raise
            error = exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = exc
        if wait is None:
            raise error
        print(f"{type(error).__name__} from {url}; retrying in {wait}s")
        time.sleep(wait)


def fetch_sofr(start, end):
    r = _get(SOFR_URL, {"startDate": start.isoformat(), "endDate": end.isoformat()})
    return parse_sofr(r.json())


def fetch_estr(start, end):
    r = _get(ESTR_URL, {"startPeriod": start.isoformat(), "endPeriod": end.isoformat(), "format": "csvdata"})
    return parse_estr(r.text)


def fetch_sonia(start, end):
    params = {"csv.x": "yes", "Datefrom": start.strftime("%d/%b/%Y"), "Dateto": end.strftime("%d/%b/%Y"),
              "SeriesCodes": "IUDSOIA", "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"}
    r = _get(SONIA_URL, params)
    return parse_sonia(r.text)


def fetch_saron(start, end):
    r = _get(SARON_URL.format(cube=SARON_CUBE), {"fromDate": start.isoformat(), "toDate": end.isoformat()})
    return parse_saron(r.text)


FETCHERS = {"USD": fetch_sofr, "EUR": fetch_estr, "GBP": fetch_sonia, "CHF": fetch_saron}


def fetch_all(start, end):
    """Download all four rates. Raises if any source fails, naming each failure."""
    frames, errors = [], []
    for ccy, fetch in FETCHERS.items():
        try:
            frames.append(fetch(start, end))
        except Exception as exc:  # report all sources, then fail
            errors.append(f"{config.OVERNIGHT_INDEX[ccy]} ({ccy}): {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError("Rate download failed:\n- " + "\n- ".join(errors))
    return pd.concat(frames, ignore_index=True)


# ---------------- daily series for the engine ----------------
def daily_rates(rates, start, end):
    """One overnight rate per currency and calendar day (weekends and holidays carry the last rate).

    Returns a DataFrame indexed by date with one column per currency.
    """
    days = pd.date_range(start - timedelta(days=10), end, freq="D").date
    wide = rates[rates["tenor"] == "ON"].pivot_table(index="rate_date", columns="currency", values="rate")
    wide = wide.reindex(days).ffill().bfill()
    missing = [c for c in config.CURRENCIES if c not in wide.columns]
    if missing:
        raise ValueError(f"No overnight rates for {missing}")
    return wide.loc[start:end, config.CURRENCIES]


def mmf_rate(on_rate):
    return on_rate + config.MMF_SPREAD_BP / 10_000


def ic_deposit_rate(on_rate):
    """TRS borrows from an entity: MMF rate - 10 bp."""
    return mmf_rate(on_rate) + config.IC_DEPOSIT_MARGIN_BP / 10_000


def ic_loan_rate(on_rate):
    """TRS lends to an entity: MMF rate + 50 bp."""
    return mmf_rate(on_rate) + config.IC_LOAN_MARGIN_BP / 10_000
