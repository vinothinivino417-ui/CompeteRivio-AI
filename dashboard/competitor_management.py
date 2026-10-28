import requests
import streamlit as st

from dashboard.business_discovery import search_business
from services.candidate_rules import CATEGORY_TAGS
from services.competitor_evidence import competitor_id
from services.competitor_selection import add_competitor, remove_competitor
from dashboard.industry_picker import industry_picker


def render_competitor_management():
    business = st.session_state.get("business_profile", {})
    search = st.session_state.get("competitor_search_key")
    scope = repr(search)
    with st.expander("Add or remove competitors"):
        st.caption("Add an actual business, then review its relevance. New entries remain unclassified. Changes keep saved history and require a new current report.")
        if notice := st.session_state.pop("_selection_notice", None):
            st.success(notice)
        with st.form("manual_competitor_form"):
            name = st.text_input("Competitor name", key="manual_competitor_name")
            address = st.text_input("Competitor address / locality", key="manual_competitor_address")
            category = industry_picker("Competitor category — select or type your own", "manual_competitor_category", search[3])
            website = st.text_input("Competitor website (optional)", key="manual_competitor_website")
            with st.expander("Business missing from the map? Enter its coordinates"):
                st.caption("Use the actual store coordinates. Leave both blank to look up mapped businesses instead.")
                latitude = st.text_input("Competitor latitude (optional)", key="manual_competitor_latitude")
                longitude = st.text_input("Competitor longitude (optional)", key="manual_competitor_longitude")
            submitted = st.form_submit_button("Find or add competitor", key="manual_competitor_submit")
        if submitted:
            st.session_state.pop("_manual_competitor_matches", None)
            try:
                if not name.strip() or not address.strip():
                    raise ValueError("Enter the competitor name and address/locality.")
                if latitude.strip() or longitude.strip():
                    add_competitor(st.session_state, name, category, latitude, longitude, address, website)
                    st.session_state["_selection_notice"] = "Competitor added. Review its classification and regenerate your report."
                    st.rerun()
                else:
                    with st.spinner("Finding competitor locations..."):
                        matches = search_business(name, address, strict_location=True)
                    if not matches:
                        st.info("No mapped business found. Check the address, or enter the actual store coordinates above.")
                    else:
                        st.session_state["_manual_competitor_matches"] = {"scope": scope, "matches": matches, "category": category, "website": website, "name": name}
            except (ValueError, requests.RequestException) as error:
                st.error(str(error))
        pending = st.session_state.get("_manual_competitor_matches", {})
        if pending.get("scope") == scope:
            matches = pending["matches"]
            choice = st.selectbox("Confirm competitor location", range(len(matches)), format_func=lambda i: matches[i].get("display_name", pending["name"]))
            if st.button("Add selected competitor", key="manual_add_match"):
                item = matches[choice]
                extra = item.get("extratags") or {}
                try:
                    add_competitor(st.session_state, item.get("name") or pending["name"], pending["category"], item.get("lat"), item.get("lon"), item.get("display_name", ""), pending["website"] or extra.get("website") or extra.get("contact:website", ""), item.get("osm_id"), item.get("osm_type"))
                    st.session_state.pop("_manual_competitor_matches", None)
                    st.session_state["_selection_notice"] = "Competitor added. Review its classification and regenerate your report."
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        selected = st.session_state.get("approved_competitors", [])
        if selected:
            target = st.selectbox("Remove from selected competitors", range(len(selected)), format_func=lambda i: f"{selected[i]['Name']} · {selected[i].get('Distance (km)', '?')} km", key="manual_remove_choice")
            if st.button("Remove selected competitor", key="manual_remove_competitor"):
                remove_competitor(st.session_state, competitor_id(selected[target]))
                st.session_state["_selection_notice"] = "Competitor removed from the selection. Saved report history is unchanged."
                st.rerun()
