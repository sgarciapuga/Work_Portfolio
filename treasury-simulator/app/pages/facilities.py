import streamlit as st

from common import config, page_header, static_data

page_header("Facilities & IV", 1,
            "TRS borrows for the IV and lends it down as IC loans when the IV buffer would fall below USD 50m.")

data, _ = static_data()
fac = data["facilities"].copy()
fac["commitment_fee_bp"] = fac["margin_bp"] * fac["commitment_fee_pct_of_margin"]

st.subheader("External facilities")
st.dataframe(fac[["facility_id", "facility_name", "currency", "limit_amount", "base_rate", "margin_bp",
                  "commitment_fee_bp", "secured", "advance_rate", "maturity_date"]],
             hide_index=True, width="stretch",
             column_config={"limit_amount": st.column_config.NumberColumn("Limit", format="localized"),
                            "commitment_fee_bp": st.column_config.NumberColumn("Commitment fee (bp)", format="%.0f")})
st.caption(f"Drawing tenor: up to {config.BRIDGE_MAX_DAYS} days to bridge a short gap; "
           f"{config.TENOR_IF_DISTRIBUTION_WITHIN_3M} month rolled if a distribution is expected within 3 months; "
           f"{config.TENOR_LONGER_NEED} months rolled for a longer need. Cheapest facility first.")

st.subheader("IV commitments book")
iv = data["iv_commitments"].copy()
iv["uncalled"] = iv["commitment"] * (1 - iv["called_pct_at_start"])
st.dataframe(iv, hide_index=True, width="stretch",
             column_config={"commitment": st.column_config.NumberColumn(format="localized"),
                            "uncalled": st.column_config.NumberColumn(format="localized"),
                            "called_pct_at_start": st.column_config.NumberColumn("Called at start", format="percent")})
st.info("Drawings, borrowing base usage and the IV buffer history arrive in Phase 4.")
