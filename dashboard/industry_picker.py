import streamlit as st

from services.candidate_rules import CATEGORY_TAGS, canonical_category


def industry_picker(label, key, value=None, persist=False):
    value = canonical_category(value) if value else value
    options = list(CATEGORY_TAGS)
    if value and value not in options:
        options.append(value)
    selected = st.selectbox(label, options, index=options.index(value) if value in options else 0,
                        key=key, accept_new_options=True,
                        persist_state="session" if persist else None,
                        help="Select a common industry, or type your own and press Enter. Custom industries without a map category support manual competitor selection; automatic discovery is not guaranteed.")
    st.caption("Not listed? Type your industry name in the dropdown and press Enter.")
    return canonical_category(selected)
