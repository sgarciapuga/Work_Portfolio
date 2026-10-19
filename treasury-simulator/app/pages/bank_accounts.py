import streamlit as st

from common import page_header, static_data

page_header("Bank accounts", 1,
            "Account inventory (BAM): TRS holds single-currency accounts; every other entity holds one "
            "multi-currency account (MCA) with a sub-account per currency, settled daily with TRS.")

data, _ = static_data()
accounts = data["accounts"].merge(data["banks"][["bank_code", "bank_name"]], on="bank_code")
accounts["mca_id"] = accounts["mca_id"].fillna("single-currency")

entity = st.selectbox("Entity", ["All"] + list(data["entities"]["entity_code"]))
shown = accounts if entity == "All" else accounts[accounts["entity_code"] == entity]
st.dataframe(shown[["account_id", "entity_code", "bank_name", "mca_id", "currency", "account_type", "purpose",
                    "signatories", "monthly_fee_usd"]], hide_index=True, width="stretch")

c1, c2 = st.columns(2)
with c1:
    st.subheader("Accounts by entity and currency")
    grid = accounts.pivot_table(index="entity_code", columns="currency", values="account_id",
                                aggfunc="count", fill_value=0)
    st.dataframe(grid.reindex(columns=["USD", "EUR", "GBP", "CHF"], fill_value=0))
with c2:
    st.subheader("Fees by bank")
    fees = accounts.groupby("bank_name", as_index=False).agg(accounts=("account_id", "count"),
                                                              monthly_fee_usd=("monthly_fee_usd", "sum"))
    st.dataframe(fees, hide_index=True)

st.subheader("Money market funds")
st.dataframe(data["mmf_funds"], hide_index=True, width="stretch")
