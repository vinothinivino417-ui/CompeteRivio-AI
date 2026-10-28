
import streamlit as st
import requests
from services.geocoding import search_places, find_area
from services.business_profiles import build_area_profile, confirm_business_profile
from dashboard.industry_picker import industry_picker


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

HEADERS = {
    "User-Agent": "CompeteRivioAI-Portfolio/1.0 (business-discovery-demo)"
}



@st.cache_data(ttl=86400, show_spinner=False)
def search_business(name, location, strict_location=False):
    queries = [f"{name}, {location}"] if strict_location else [
        f"{name}, {location}",
        f"{name}, Chennai",
        name,
    ]

    for query in queries:
        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "limit": 10,
            "countrycodes": "in",
        }
        if strict_location:
            params.pop("countrycodes", None)

        results = search_places(params)

        if results:
            return results

    return []



def render_business_discovery():
    st.subheader("Business Profile Resolution")
    st.caption(
        "Search OpenStreetMap business listings and "
        "confirm the correct profile."
    )

    with st.form("business_profile_form"):
        business_name = st.text_input(
            "Business Name",
            placeholder="Example: ABC Digital Marketing",
        )

        location = st.text_input(
            "Business Location",
            placeholder="Chennai, Tamil Nadu",
        )

        industry = industry_picker("Industry / Business Category — select or type your own", "business_profile_industry")

        website = st.text_input(
            "Website (Optional)",
            placeholder="https://example.com",
        )

        submitted = st.form_submit_button(
            "Search Business",
            type="primary",
        )

    if submitted:
        if not business_name.strip() or not location.strip():
            st.warning("Enter Business Name and Location.")
        else:
            st.session_state.pop("_manual_area_profile", None)

            with st.status("Searching for your business... Please wait.", expanded=True) as search_status:
                st.write("Looking up matching business profiles on OpenStreetMap.")
                try:
                    results = search_business(
                        business_name.strip(),
                        location.strip(),
                    )
                    search_status.update(label=f"Search complete: {len(results)} matches found", state="complete", expanded=False)
                except requests.RequestException as error:
                    search_status.update(label="Business search failed. Please retry.", state="error", expanded=True)
                    st.error(f"Search failed: {error}")
                    results = []

            st.session_state["business_search_results"] = results
            st.session_state["business_search_input"] = {
                "name": business_name.strip(),
                "location": location.strip(),
                "industry": industry.strip(),
                "website": website.strip(),
            }

    results = st.session_state.get(
        "business_search_results", []
    )
    entered = st.session_state.get(
        "business_search_input", {}
    )

    if entered:
        st.divider()
        st.subheader("Business Search Results")

        if results:
            options = list(range(len(results)))

            selected_index = st.selectbox(
                "Select matching business",
                options,
                format_func=lambda i: results[i].get(
                    "display_name", "Unnamed business"
                ),
            )

            selected = results[selected_index]
            extra = selected.get("extratags") or {}

            profile = {
                "name": selected.get("name")
                    or entered["name"],
                "location": selected.get("display_name", ""),
                "industry": entered["industry"],
                "website": extra.get("website")
                    or extra.get("contact:website")
                    or entered["website"],
                "latitude": float(selected["lat"]),
                "longitude": float(selected["lon"]),
                "osm_id": selected.get("osm_id"),
                "osm_type": selected.get("osm_type"),
                "source": "OpenStreetMap",
            }

            st.write("**Business:**", profile["name"])
            st.write("**Address:**", profile["location"])
            st.write(
                "**Category:**",
                selected.get("type", "Unknown"),
            )
            st.write(
                "**Website:**",
                profile["website"] or "Not available",
            )

            st.map([{
                "lat": profile["latitude"],
                "lon": profile["longitude"],
            }])

            if st.button(
                "Confirm Business",
                type="primary",
                key="confirm_osm_business",
            ):
                confirm_business_profile(st.session_state, profile)
                st.rerun()

        else:
            st.warning(
                "No matching OpenStreetMap listing found. "
                "Locate and confirm the entered area to search nearby. Use a locality or street address, not only a city."
            )

            if st.button("Find area for entered business", key="find_manual_business_area"):
                try:
                    with st.spinner("Locating the entered area..."):
                        areas = find_area(entered["location"])
                    if not areas:
                        raise ValueError("Area not found. Enter the street/locality, city and country.")
                    st.session_state["_manual_area_profile"] = {"input": dict(entered), "profile": build_area_profile(entered, areas[0])}
                except (ValueError, requests.RequestException) as error:
                    st.error(str(error))
            pending = st.session_state.get("_manual_area_profile", {})
            if pending.get("input") == entered:
                profile = pending["profile"]
                st.write("**Area found:**", profile["location"])
                st.warning("This is an approximate area centre, not a verified store location. Distances and nearby candidates need review.")
                st.map([{"lat": profile["latitude"], "lon": profile["longitude"]}])
                if st.button("Confirm approximate area", key="confirm_manual_business_area"):
                    confirm_business_profile(st.session_state, profile)
                    st.rerun()

    if st.session_state.get("business_confirmed"):
        profile = st.session_state.get("business_profile", {})
        if profile.get("latitude") is None or profile.get("longitude") is None:
            st.warning("This older manual profile has no location coordinates. Find and confirm its area above before searching competitors.")
        else:
            st.success("Business profile confirmed!")
        st.write("**Selected business:**", profile.get("name"))
        st.write("**Source:**", profile.get("source"))

    st.caption("Business data © OpenStreetMap contributors")
