from datetime import datetime, timezone
import hashlib
import json

import pandas as pd
import streamlit as st

from services.google_places import fetch_google_rating, is_configured


def render_google_ratings():
    business = st.session_state.get("business_profile", {})
    competitors = st.session_state.get("approved_competitors", [])
    identity = hashlib.sha256(json.dumps([business, competitors], sort_keys=True, default=str).encode()).hexdigest()
    with st.expander("Google ratings · optional live API"):
        st.caption("Google Places is separate from Gemini. Requires a server-side GOOGLE_PLACES_API_KEY, Places API (New), and enabled Google Cloud billing. Searches request rating fields and may incur Enterprise-tier charges.")
        if not is_configured():
            st.info("Google Places key not configured. Your trainer can add GOOGLE_PLACES_API_KEY to the local .env file and restart the app. Free discovery and reports work without it.")
            return
        st.caption("Key configured. Requests run only when you click the button. Names and mapped coordinates are sent to Google. Results are temporary, shown separately, and excluded from local history, PDF/CSV exports, AI prompts, scores and the OpenStreetMap map.")
        targets = [(business.get("name", "Your business"), business.get("latitude"), business.get("longitude"))]
        if business.get("resolution_status") == "area_center":
            targets = []
            st.caption("Your store's location is approximate, so its Google lookup is skipped until the correct business is confirmed.")
        targets += [(row.get("Name", "Business"), row.get("Latitude"), row.get("Longitude")) for row in competitors]
        if not targets:
            return
        limit = st.number_input("Maximum Google searches this click", min_value=1, max_value=min(16, len(targets)), value=min(5, len(targets)), step=1, key="google_rating_limit")
        if st.button("Fetch live Google ratings (may incur charges)", key="fetch_google_ratings"):
            rows = []
            with st.status("Checking Google business matches...", expanded=True) as status:
                indicator = st.progress(0)
                for index, (name, lat, lon) in enumerate(targets[:limit]):
                    rows.append(fetch_google_rating(name, lat, lon))
                    indicator.progress((index + 1) / limit)
                status.update(label="Google lookup finished — check match notes", state="complete", expanded=False)
            st.session_state["_google_live_ratings"] = {"identity": identity, "rows": rows, "time": datetime.now(timezone.utc).timestamp()}
        result = st.session_state.get("_google_live_ratings", {})
        if result and (result.get("identity") != identity or datetime.now(timezone.utc).timestamp() - result.get("time", 0) > 900):
            st.session_state.pop("_google_live_ratings", None)
            result = {}
        if result:
            st.markdown("**Google Maps**")
            st.caption("Live third-party ratings · cleared on the next panel refresh after 15 minutes. No export is provided. Verify branch addresses before interpretation.")
            rows = result["rows"]
            st.dataframe(pd.DataFrame([{key: value for key, value in row.items() if key != "Attributions"} for row in rows]),
                         hide_index=True, width="stretch",
                         column_config={"Google Maps URL": st.column_config.LinkColumn("Open in Google Maps")})
            for row in rows:
                for attribution in row.get("Attributions", []) if isinstance(row.get("Attributions", []), list) else []:
                    if isinstance(attribution, dict):
                        st.text("Data provider: " + str(attribution.get("provider", "Google Maps")))
            if st.button("Clear live Google results", key="clear_google_ratings"):
                st.session_state.pop("_google_live_ratings", None)
                st.rerun()
        st.caption("Use is subject to Google Maps Platform Terms and Privacy Policy. This panel does not automatically populate the manual evidence table.")
        st.markdown("[Google Maps terms](https://cloud.google.com/maps-platform/terms) · [Google privacy policy](https://policies.google.com/privacy)")
