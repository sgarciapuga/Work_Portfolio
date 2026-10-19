import streamlit as st

from common import config, glossary, page_header, tier_badge

page_header("Learn", 4, "Glossary by tier: how deeply each topic is built into the simulator.")

terms = glossary()
for tier, label in config.TIERS.items():
    st.markdown(f"### {tier_badge(tier)}", unsafe_allow_html=True)
    for _, row in terms[terms["tier"] == tier].iterrows():
        with st.expander(row["term"]):
            st.write(row["definition"])
            if row["example"]:
                st.caption(f"Example: {row['example']}")
