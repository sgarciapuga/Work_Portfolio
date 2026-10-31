from datetime import date

import pandas as pd
import pytest
import requests

from tsim import rates

SOFR_JSON = {"refRates": [
    {"effectiveDate": "2025-01-02", "type": "SOFR", "percentRate": 4.41, "volumeInBillions": 2200},
    {"effectiveDate": "2025-01-03", "type": "SOFR", "percentRate": 4.31},
]}
ESTR_CSV = """KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,OBS_STATUS
EST.B.EU000A2X2A25.WT,B,EU,2025-01-02,2.917,A
EST.B.EU000A2X2A25.WT,B,EU,2025-01-03,2.920,A
"""
SONIA_CSV = """DATE,IUDSOIA
02 Jan 2025,4.7000
03 Jan 2025,4.6990
"""
SARON_CSV = '''"CubeId";"snbgwdzid"
"PublishingDate";"2025-01-06 09:00"

"Date";"D0";"Value"
"2025-01-03";"LZ";"0.5"
"2025-01-03";"SARON";"0.452"
"2025-01-06";"SARON";"0.449"
'''


def test_parsers_return_decimal_rates():
    sofr = rates.parse_sofr(SOFR_JSON)
    assert list(sofr["rate"]) == pytest.approx([0.0441, 0.0431])
    assert set(sofr["currency"]) == {"USD"}
    assert rates.parse_estr(ESTR_CSV)["rate"].iloc[0] == pytest.approx(0.02917)
    assert rates.parse_sonia(SONIA_CSV)["rate_date"].iloc[1] == date(2025, 1, 3)
    saron = rates.parse_saron(SARON_CSV)
    assert len(saron) == 2 and saron["rate"].iloc[0] == pytest.approx(0.00452)


def test_parsers_fail_loudly_on_a_new_format():
    with pytest.raises(ValueError):
        rates.parse_estr("a,b\n1,2\n")
    with pytest.raises(ValueError):
        rates.parse_saron("nothing useful here")


def test_daily_rates_fill_weekends_and_pricing_margins():
    df = pd.concat([rates.parse_sofr(SOFR_JSON), rates.parse_estr(ESTR_CSV),
                    rates.parse_sonia(SONIA_CSV), rates.parse_saron(SARON_CSV)])
    daily = rates.daily_rates(df, date(2025, 1, 2), date(2025, 1, 6))
    assert daily.loc[date(2025, 1, 5), "USD"] == pytest.approx(0.0431)     # Sunday carries Friday
    assert daily.loc[date(2025, 1, 6), "CHF"] == pytest.approx(0.00449)
    on = 0.04
    assert rates.mmf_rate(on) == pytest.approx(0.0395)
    assert rates.ic_deposit_rate(on) == pytest.approx(0.0385)
    assert rates.ic_loan_rate(on) == pytest.approx(0.0445)


# ---------------- retries on temporary download failures ----------------
def _response(status, text=""):
    r = requests.Response()
    r.status_code, r.url, r._content = status, "https://example.test/rates", text.encode()
    return r


@pytest.fixture
def server(monkeypatch):
    """Replay a list of responses (or exceptions) for requests.get; record the waits."""
    calls, waits = [], []

    def install(*outcomes):
        queue = list(outcomes)

        def fake_get(url, **kwargs):
            calls.append(url)
            outcome = queue.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(rates.requests, "get", fake_get)
        monkeypatch.setattr(rates.time, "sleep", waits.append)
        return calls, waits

    return install


def test_download_retries_a_server_error_and_succeeds(server):
    calls, waits = server(_response(500), _response(200, SONIA_CSV))
    sonia = rates.fetch_sonia(date(2025, 1, 2), date(2025, 1, 3))
    assert len(sonia) == 2
    assert len(calls) == 2 and waits == [rates.RETRY_WAITS[0]]


def test_download_retries_timeouts_and_dropped_connections(server):
    calls, waits = server(requests.Timeout(), requests.ConnectionError(), _response(200, ESTR_CSV))
    assert len(rates.fetch_estr(date(2025, 1, 2), date(2025, 1, 3))) == 2
    assert waits == list(rates.RETRY_WAITS)


def test_download_gives_up_after_three_attempts(server):
    calls, waits = server(_response(500), _response(502), _response(503))
    with pytest.raises(requests.HTTPError, match="503"):
        rates.fetch_sonia(date(2025, 1, 2), date(2025, 1, 3))
    assert len(calls) == 3 and waits == list(rates.RETRY_WAITS)


def test_download_does_not_retry_a_client_error(server):
    calls, waits = server(_response(404))
    with pytest.raises(requests.HTTPError, match="404"):
        rates.fetch_sonia(date(2025, 1, 2), date(2025, 1, 3))
    assert len(calls) == 1 and waits == []
