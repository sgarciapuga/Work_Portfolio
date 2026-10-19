"""Load and check the static data in treasury-simulator/static/.

The static CSVs are written by hand (they are seed data, not pipeline outputs).
`load_static()` returns one DataFrame per file; `validate()` returns a list of
problems, empty when everything links up.
"""

import re
from pathlib import Path

import pandas as pd

from tsim.config import CURRENCIES

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

TABLES = {
    "entities": "entity_code",
    "banks": "bank_code",
    "accounts": "account_id",
    "flow_codes": "flow_code",
    "fee_schedule": "schedule_id",
    "iv_commitments": "investment_id",
    "facilities": "facility_id",
    "mmf_funds": "fund_id",
}

FREQUENCIES = {"monthly", "semi_monthly", "quarterly", "annual"}
# day_rule tokens, separated by "|": day:N, bd:N, last_bd, or MM-DD (quarterly/annual)
DAY_RULE_TOKEN = re.compile(r"^(day:(?:[1-9]|[12]\d|3[01])|bd:(?:[1-9]|1\d|2[0-3])|last_bd|(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))$")


def load_static(static_dir=STATIC_DIR):
    """Return {table name: DataFrame} for every static CSV."""
    static_dir = Path(static_dir)
    data = {}
    for name in TABLES:
        data[name] = pd.read_csv(static_dir / f"{name}.csv", keep_default_na=False, na_values=[""])
    return data


def _check_unique(df, key, name, problems):
    dupes = df[df[key].duplicated()][key].tolist()
    if dupes:
        problems.append(f"{name}: duplicate {key} {dupes}")


def _check_in(values, allowed, label, problems):
    bad = sorted(set(values) - set(allowed))
    if bad:
        problems.append(f"{label}: unknown values {bad}")


def _check_day_rule(rule, frequency):
    tokens = str(rule).split("|")
    if not all(DAY_RULE_TOKEN.match(t) for t in tokens):
        return False
    dated = [t for t in tokens if re.match(r"^\d\d-\d\d$", t)]
    if frequency in ("monthly", "semi_monthly"):
        return not dated and len(tokens) == (2 if frequency == "semi_monthly" else 1)
    expected = 4 if frequency == "quarterly" else None
    return len(dated) == len(tokens) and (expected is None or len(tokens) == expected)


def validate(data):
    """Return a list of problems in the static data (empty list = all good)."""
    problems = []
    for name, key in TABLES.items():
        _check_unique(data[name], key, name, problems)

    entities = set(data["entities"]["entity_code"])
    banks = set(data["banks"]["bank_code"])
    flows = set(data["flow_codes"]["flow_code"])

    acc = data["accounts"]
    _check_in(acc["entity_code"], entities, "accounts.entity_code", problems)
    _check_in(acc["bank_code"], banks, "accounts.bank_code", problems)
    _check_in(acc["currency"], CURRENCIES, "accounts.currency", problems)
    _check_in(data["entities"]["functional_ccy"], CURRENCIES, "entities.functional_ccy", problems)

    # Every entity needs an operating account in its functional currency;
    # TRS needs one in every currency.
    operating = acc[acc["account_type"] == "operating"]
    for _, ent in data["entities"].iterrows():
        needed = CURRENCIES if ent["entity_code"] == "TRS" else [ent["functional_ccy"]]
        have = set(operating.loc[operating["entity_code"] == ent["entity_code"], "currency"])
        missing = [c for c in needed if c not in have]
        if missing:
            problems.append(f"accounts: {ent['entity_code']} has no operating account in {missing}")

    # Entity accounts grouped in a multi-currency account (MCA) belong to one entity and one bank.
    mca = acc[acc["mca_id"].notna()]
    for mca_id, grp in mca.groupby("mca_id"):
        if grp["entity_code"].nunique() > 1 or grp["bank_code"].nunique() > 1:
            problems.append(f"accounts: MCA {mca_id} mixes entities or banks")

    fees = data["fee_schedule"]
    _check_in(fees["entity_code"], entities, "fee_schedule.entity_code", problems)
    _check_in(fees["flow_code"], flows, "fee_schedule.flow_code", problems)
    _check_in(fees["currency"], CURRENCIES, "fee_schedule.currency", problems)
    _check_in(fees["frequency"], FREQUENCIES, "fee_schedule.frequency", problems)
    _check_in(fees["counterparty_entity"].dropna(), entities, "fee_schedule.counterparty_entity", problems)
    for _, row in fees.iterrows():
        if not _check_day_rule(row["day_rule"], row["frequency"]):
            problems.append(f"fee_schedule {row['schedule_id']}: day_rule '{row['day_rule']}' does not fit {row['frequency']}")

    # Every currency an entity receives or pays needs an operating account in that currency.
    have = set(zip(operating["entity_code"], operating["currency"]))
    needed = set(zip(fees["entity_code"], fees["currency"]))
    for ent, ccy in sorted(needed - have):
        problems.append(f"accounts: {ent} has flows in {ccy} but no {ccy} operating account")

    # Intercompany recharges must net to zero per currency (one side pays, the other receives).
    ic = fees[fees["counterparty_entity"].notna()]
    for ccy, total in ic.groupby("currency")["amount"].sum().items():
        if abs(total) > 0.01:
            problems.append(f"fee_schedule: intercompany flows in {ccy} do not net to zero ({total:,.0f})")

    iv = data["iv_commitments"]
    _check_in(iv["currency"], CURRENCIES, "iv_commitments.currency", problems)
    bad_pct = iv[(iv["called_pct_at_start"] < 0) | (iv["called_pct_at_start"] > 1)]["investment_id"].tolist()
    if bad_pct:
        problems.append(f"iv_commitments: called_pct_at_start outside 0-1 for {bad_pct}")

    fac = data["facilities"]
    _check_in(fac["currency"], CURRENCIES, "facilities.currency", problems)
    _check_in(fac["agent_bank"], banks, "facilities.agent_bank", problems)
    secured = fac[fac["secured"].astype(str).str.lower() == "true"]
    if secured["advance_rate"].isna().any():
        problems.append("facilities: a secured facility needs an advance_rate")

    mmf = data["mmf_funds"]
    _check_in(mmf["currency"], CURRENCIES, "mmf_funds.currency", problems)
    _check_in(mmf["bank_code"], banks, "mmf_funds.bank_code", problems)

    return problems


def summary(data):
    """A few headline numbers, used by the README check and the app's Overview."""
    iv = data["iv_commitments"]
    fac = data["facilities"]
    return {
        "entities": len(data["entities"]),
        "accounts": len(data["accounts"]),
        "iv_investments": len(iv),
        "iv_commitments_by_ccy": iv.groupby("currency")["commitment"].sum().to_dict(),
        "facility_limit_usd": float(fac.loc[fac["currency"] == "USD", "limit_amount"].sum()),
    }
