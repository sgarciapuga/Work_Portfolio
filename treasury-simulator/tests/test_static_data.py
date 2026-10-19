import pandas as pd
import pytest

from tsim import config
from tsim.static_data import load_static, summary, validate


@pytest.fixture(scope="module")
def data():
    return load_static()


def test_static_data_has_no_problems(data):
    assert validate(data) == []


def test_six_entities_with_trs_as_in_house_bank(data):
    ent = data["entities"].set_index("entity_code")
    assert list(ent.index) == ["TRS", "IV", "MGT", "US", "CH", "EU"]
    assert ent.loc["TRS", "role"] == "treasury"
    assert ent.loc["TRS", "functional_ccy"] == "USD"


def test_iv_commitments_about_usd_1_5bn(data):
    # Rough USD equivalents; real rates come from the FX feed in later phases.
    approx = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CHF": 1.13}
    iv = data["iv_commitments"]
    total = (iv["commitment"] * iv["currency"].map(approx)).sum()
    assert 1.4e9 < total < 1.7e9


def test_facilities_match_design(data):
    fac = data["facilities"].set_index("facility_id")
    assert fac.loc["SEC1", "limit_amount"] == 300_000_000
    assert fac.loc["SEC1", "margin_bp"] == 150
    assert fac.loc["RCF1", "limit_amount"] == 200_000_000
    assert fac.loc["RCF1", "margin_bp"] == 200
    assert (fac["commitment_fee_pct_of_margin"] == 0.35).all()


def test_config_matches_design():
    assert config.OPERATING_MIN_USD == 100_000
    assert config.FX_TOLERANCE_USD == 50_000
    assert config.IV_BUFFER_USD == 50_000_000
    assert config.IC_LOAN_MARGIN_BP == 50
    assert config.IC_DEPOSIT_MARGIN_BP == -10
    assert config.HISTORY_START.isoformat() == "2025-01-01"


def test_validate_catches_broken_links(data):
    broken = {k: v.copy() for k, v in data.items()}
    broken["accounts"].loc[0, "bank_code"] = "NOPE"
    broken["fee_schedule"].loc[0, "day_rule"] = "day:40"
    extra = pd.DataFrame([{**broken["fee_schedule"].iloc[-1].to_dict(), "schedule_id": "FX1", "amount": 5}])
    broken["fee_schedule"] = pd.concat([broken["fee_schedule"], extra], ignore_index=True)
    problems = " | ".join(validate(broken))
    assert "accounts.bank_code" in problems
    assert "day_rule 'day:40'" in problems
    assert "do not net to zero" in problems


def test_every_flow_currency_has_an_account(data):
    broken = {k: v.copy() for k, v in data.items()}
    broken["accounts"] = broken["accounts"][broken["accounts"]["account_id"] != "US-BKA-GBP"]
    problems = " | ".join(validate(broken))
    assert "US has flows in GBP but no GBP operating account" in problems


def test_entities_hold_multi_currency_accounts(data):
    acc = data["accounts"]
    for ent in ["IV", "MGT", "US", "CH", "EU"]:
        sub = acc[acc["entity_code"] == ent]
        assert sub["mca_id"].nunique() == 1
        assert set(sub["currency"]) == {"USD", "EUR", "GBP", "CHF"}


def test_summary_counts(data):
    s = summary(data)
    assert s["entities"] == 6
    assert s["iv_investments"] == 12
    assert s["facility_limit_usd"] == 500_000_000
