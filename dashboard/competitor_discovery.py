import math
import requests
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timezone

from dashboard.theme import THEMES
from services.geocoding import find_nearby_places
from services.ai_insights import classify_competitors_with_gemini
from services.candidate_rules import CATEGORY_TAGS, category_filters, is_directory, normalized_name, valid_coordinates, relevance_fields, ranked
from services.competitor_evidence import competitor_id
from dashboard.industry_picker import industry_picker
from dashboard.navigation import navigate_to


# ==========================================
# CONFIGURATION
# ==========================================

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# ==========================================
# DISTANCE CALCULATION
# ==========================================

def calculate_distance(lat1, lon1, lat2, lon2):
    radius = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return 2 * radius * math.asin(
        min(1, math.sqrt(a))
    )


# ==========================================
# OVERPASS API SEARCH
# ==========================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nearby_businesses(lat, lon, category, radius):
    from services.candidate_rules import canonical_category
    category = canonical_category(category)
    if not category_filters(category):
        return []  # Never interpolate custom industry text into an Overpass query.
    tag_key, tag_value = CATEGORY_TAGS[category]

    query = f"""
[out:json][timeout:15];
nwr["{tag_key}"="{tag_value}"]["name"]
(around:{radius},{lat},{lon});
out center 50;
"""
    if len(category_filters(category)) > 1:
        selectors = "\n".join(f'nwr["{key}"="{value}"]["name"](around:{radius},{lat},{lon});' for key, value in category_filters(category))
        query = f"[out:json][timeout:15];\n(\n{selectors}\n);\nout center 50;"

    last_error = None
    fallback_tried = False

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={
                    "User-Agent": "CompeteRivioAI-Portfolio/1.0"
                },
                timeout=(10, 30),
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                raise ValueError(
                    "Unexpected Overpass response format."
                )

            # Overpass can return HTTP 200 with a runtime error and partial data.
            if data.get("remark"):
                raise ValueError(str(data["remark"]))

            elements = data.get("elements")
            if not isinstance(elements, list):
                raise ValueError("Overpass response is missing business results.")

            return elements

        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
            ValueError,
        ) as error:
            last_error = str(error)

        # Try one bounded, cached shortlist before waiting on more Overpass hosts.
        if not fallback_tried:
            fallback_tried = True
            try:
                fallback = []
                for fallback_key, fallback_value in category_filters(category):
                    try:
                        fallback.extend(find_nearby_places(lat, lon, fallback_key, fallback_value, radius))
                    except (requests.RequestException, ValueError) as error:
                        last_error = f"Nearby-place fallback: {error}"
                if fallback:
                    return fallback
            except (requests.RequestException, ValueError) as error:
                last_error = f"Nearby-place fallback: {error}"

    raise requests.RequestException(
        "Overpass API servers are currently unavailable. "
        "Please wait before retrying. "
        f"Last error: {last_error}"
    )


# ==========================================
# PROCESS SEARCH RESULTS
# ==========================================

def process_competitors(elements, business, category):
    lat, lon = valid_coordinates(business["latitude"], business["longitude"])

    competitors = []
    seen = set()
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for item in elements:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags", {})
        if not isinstance(tags, dict) or not isinstance(tags.get("name", ""), str):
            continue
        name = tags.get("name", "").strip()

        if not name or is_directory(name, tags.get("website") or tags.get("contact:website", ""), tags):
            continue

        item_lat = item.get("lat")
        item_lon = item.get("lon")

        if item_lat is None or item_lon is None:
            center = item.get("center") or {}
            item_lat = center.get("lat")
            item_lon = center.get("lon")

        if item_lat is None or item_lon is None:
            continue

        try:
            item_lat, item_lon = valid_coordinates(item_lat, item_lon)
        except ValueError:
            continue

        # Exclude the confirmed business.
        if (
            str(item.get("id")) == str(business.get("osm_id"))
            and item.get("type") == business.get("osm_type")
        ):
            continue

        # Remove duplicate listings.
        unique_key = (item.get("type"), str(item.get("id"))) if item.get("id") is not None else (normalized_name(name), item_lat, item_lon)

        if unique_key in seen:
            continue

        if any(normalized_name(name) == normalized_name(row["Name"]) and calculate_distance(item_lat, item_lon, row["Latitude"], row["Longitude"]) < 0.05 for row in competitors):
            continue

        seen.add(unique_key)

        distance = calculate_distance(
            lat,
            lon,
            item_lat,
            item_lon,
        )

        from services.candidate_rules import same_business_listing
        if same_business_listing(business, tags, distance):
            continue

        competitors.append({
            "Name": name,
            "Website": tags.get("website") or tags.get("contact:website", ""),
            "Category": category,
            "Distance (km)": round(distance, 2),
            "Latitude": item_lat,
            "Longitude": item_lon,
            "OSM ID": str(item.get("id")),
            "OSM Type": item.get("type", ""),
            "Classification": "Not classified",
            "Confidence": "N/A",
            "AI Reason": "",
            "Discovery source": item.get("discovery_source", "OpenStreetMap Overpass"),
            "Processed at (UTC)": retrieved,
            **relevance_fields(tags, category, distance),
        })

    return ranked(competitors)


# ==========================================
# MAIN DASHBOARD
# ==========================================

def render_approved_comparison(approved, business_name, area_based=False):
    st.divider()
    st.subheader("Selected business comparison")
    st.caption(f"Compare nearby businesses with {business_name}.")
    if any("limited best matches" in row.get("Discovery source", "") for row in approved):
        st.info("The primary map service was unavailable. These are limited nearby best matches from the fallback search, not an exhaustive competitor list.")
    comparison = pd.DataFrame(approved).reindex(columns=[
        "Name", "Category", "Distance (km)", "Classification",
        "Confidence", "AI Reason", "Discovery source", "OSM ID", "OSM Type",
    ])
    comparison["Classification"] = comparison["Classification"].fillna("Not classified")
    comparison["Distance (km)"] = pd.to_numeric(comparison["Distance (km)"], errors="coerce")
    comparison = comparison.sort_values("Distance (km)", na_position="last")
    total_col, direct_col, indirect_col = st.columns(3)
    has_classification = comparison["Classification"].isin(["Direct", "Indirect", "Irrelevant"]).any()
    total_col.metric("Selected businesses", len(comparison))
    direct_col.metric("Direct competitors", int(comparison["Classification"].eq("Direct").sum()) if has_classification else "Unavailable")
    indirect_col.metric("Indirect competitors", int(comparison["Classification"].eq("Indirect").sum()) if has_classification else "Unavailable")
    other_count = int((~comparison["Classification"].isin(["Direct", "Indirect"])).sum())
    if other_count:
        st.caption(f"{other_count} selected businesses have another classification or are not classified yet. Unavailable means classification has not completed, not that there are no competitors.")
    chart_data = comparison.dropna(subset=["Distance (km)"]).copy()
    if not chart_data.empty:
        duplicate_names = chart_data["Name"].duplicated(keep=False)
        chart_data["Business"] = chart_data["Name"]
        chart_data.loc[duplicate_names, "Business"] = chart_data.loc[duplicate_names].apply(
            lambda row: f"{row['Name']} ({row['OSM Type']} {row['OSM ID']})", axis=1
        )
        st.write("**Distance from the area centre (approximate)**" if area_based else "**Distance from your business**")
        mode = st.session_state.get("appearance_mode") or "Dark"
        colors = THEMES.get(mode, THEMES["Dark"])
        distance_chart = px.bar(
            chart_data, x="Distance (km)", y="Business", orientation="h",
            text="Distance (km)",
            category_orders={"Business": chart_data["Business"].tolist()},
        )
        distance_chart.update_traces(
            marker_color=colors["accent"], texttemplate="%{x:.2f} km",
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br>Distance: %{x:.2f} km<extra></extra>",
        )
        distance_chart.update_layout(
            template="streamlit", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            height=max(350, min(1000, len(chart_data) * 38 + 100)),
            margin=dict(l=20, r=85, t=20, b=40),
            xaxis=dict(title="Distance (km)", rangemode="tozero"),
            yaxis=dict(title=None, automargin=True),
        )
        st.plotly_chart(distance_chart, width="stretch", theme="streamlit")
    st.caption("Distances are straight-line estimates, not travel distances. Distance alone does not measure competitive strength.")
    st.dataframe(
        comparison.drop(columns=["OSM ID", "OSM Type"]), hide_index=True, width="stretch",
        column_config={"Distance (km)": st.column_config.NumberColumn(format="%.2f km")},
    )
    st.download_button(
        "Download approved competitors (CSV)",
        data=comparison.to_csv(index=False).encode("utf-8-sig"),
        file_name="CompeteRivio_Approved_Competitors.csv", mime="text/csv",
        key="download_approved_competitors",
    )


def _offer_saved_selection():
    business = st.session_state.get("business_profile", {})
    search = st.session_state.get("competitor_search_key")
    approved = st.session_state.get("approved_competitors", [])
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not search or len(search) != 5 or tuple(search[:3]) != identity or not approved:
        return
    st.info(f"Your saved selection is still available: {len(approved)} business(es) · {search[3]} · {search[4]} km search radius. The failed/new search has not replaced it.")
    st.button("Open saved results", key="open_saved_competitor_results", on_click=navigate_to, args=("Overview",))


def render_competitor_discovery():

    st.subheader("Competitor Discovery")

    st.caption(
        "Discover nearby businesses using OpenStreetMap "
        "and classify them with Gemini AI."
    )

    # --------------------------------------
    # CHECK CONFIRMED BUSINESS
    # --------------------------------------

    if not st.session_state.get("business_confirmed"):
        st.warning(
            "Please confirm your business in "
            "Business & Discovery first."
        )
        return

    business = st.session_state.get(
        "business_profile", {}
    )

    st.success(
        f"Confirmed Business: "
        f"{business.get('name', 'Unknown')}"
    )

    if (
        "latitude" not in business
        or "longitude" not in business
    ):
        st.warning(
            "Business coordinates are unavailable. "
            "Select an OpenStreetMap result in "
            "Business & Discovery."
        )
        return

    lat = float(business["latitude"])
    lon = float(business["longitude"])

    # --------------------------------------
    # SEARCH SETTINGS
    # --------------------------------------

    category = industry_picker("Business Category — select or type your own", "competitor_category", st.session_state.get("competitor_category"), persist=True)
    if category not in CATEGORY_TAGS:
        st.info("This custom industry has no automatic map category. Click Discover Competitors to prepare a manual selection, then use Add or remove competitors. No unrelated category will be substituted.")

    radius_km = st.slider(
        "Search Radius (km)",
        min_value=1,
        max_value=20,
        value=3,
        key="competitor_radius",
        persist_state="session",
    )

    search_key = (
        str(business.get("osm_id")),
        lat,
        lon,
        category,
        radius_km,
    )

    # --------------------------------------
    # DISCOVER COMPETITORS
    # --------------------------------------

    if st.button(
        "Discover Competitors",
        type="primary",
        key="discover_competitors_button",
    ):

        with st.status(
            "Searching nearby businesses... Please wait.", expanded=True
        ) as search_status:
            st.write("Checking map servers. This may take a minute.")

            try:
                elements = fetch_nearby_businesses(
                    lat,
                    lon,
                    category,
                    radius_km * 1000,
                )

                competitors = process_competitors(
                    elements,
                    business,
                    category,
                )

                st.session_state[
                    "discovered_competitors"
                ] = competitors

                st.session_state[
                    "competitor_search_key"
                ] = search_key
                st.session_state["competitor_selection_mode"] = "manual"
                st.session_state["automatic_warnings"] = []

                # Clear outdated classifications
                # and approvals after a new search.
                st.session_state.pop(
                    "classified_competitors", None
                )

                st.session_state.pop(
                    "approved_competitors", None
                )

                st.success(
                    f"{len(competitors)} businesses found!"
                )
                search_status.update(label="Competitor search complete", state="complete", expanded=False)

            except requests.RequestException as error:
                search_status.update(label="Search could not finish. Please retry.", state="error", expanded=True)
                st.warning(
                    "The map data service could not complete this search. "
                    "Try a smaller search radius, or wait a minute and "
                    "click Discover Competitors again."
                )
                _offer_saved_selection()
                with st.expander("Search error details"):
                    st.code(str(error), language=None)
                return

    # --------------------------------------
    # LOAD EXISTING RESULTS
    # --------------------------------------

    saved_key = st.session_state.get(
        "competitor_search_key"
    )

    if saved_key != search_key:
        st.info(
            "Click Discover Competitors to search "
            "with the selected settings."
        )
        _offer_saved_selection()
        return

    from dashboard.competitor_management import render_competitor_management
    render_competitor_management()

    competitors = st.session_state.get(
        "discovered_competitors"
    )

    if competitors is None:
        return

    if not competitors:
        st.info(
            "No businesses found. "
            "Try a larger search radius."
        )
        return

    # --------------------------------------
    # COMPETITOR RESULTS
    # --------------------------------------

    st.divider()
    st.subheader("Discovered Competitors")
    st.caption("Local relevance estimate: 70 × category evidence (1 exact, 0.5 related/unverified, 0 different) + 30 / (1 + distance in km). Search prominence is unavailable. Known directory/aggregator patterns and duplicate listings are filtered; review is still needed.")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Businesses Found",
            len(competitors),
        )

    with col2:
        st.metric(
            "Search Radius",
            f"{radius_km} km",
        )

    df = pd.DataFrame(competitors)

    st.dataframe(
        df.reindex(columns=["Name", "Category", "Distance (km)", "Relevance score", "Category evidence"]),
        hide_index=True,
        width="stretch",
    )

    # --------------------------------------
    # COMPETITOR MAP
    # --------------------------------------

    st.divider()
    st.subheader("Competitor Locations")

    map_rows = [
        {
            "lat": lat,
            "lon": lon,
        }
    ]

    for competitor in competitors:
        map_rows.append({
            "lat": competitor["Latitude"],
            "lon": competitor["Longitude"],
        })

    st.map(pd.DataFrame(map_rows))

    st.caption(
        "Map includes the confirmed business "
        "and discovered nearby businesses."
    )

    # --------------------------------------
    # GEMINI AI CLASSIFICATION
    # --------------------------------------

    st.divider()
    st.subheader(
        "Gemini AI Competitor Classification"
    )

    st.caption(
        "Gemini estimates whether businesses are "
        "direct, indirect, or irrelevant competitors. "
        "Review classifications before approval."
    )

    classification_limit = st.number_input(
        "Number of businesses to classify",
        min_value=1,
        max_value=len(competitors),
        value=min(10, len(competitors)),
        step=1,
        key="competitor_classification_limit",
        persist_state="session",
        help=(
            "Start with 10 businesses to reduce "
            "Gemini API usage."
        ),
    )

    if st.button(
        "Classify Competitors with Gemini",
        type="primary",
        key="classify_competitors_ai",
    ):

        with st.status(
            "Gemini is classifying competitors... Please wait.", expanded=True
        ) as classification_status:
            st.write("Analyzing the selected businesses. Results will appear below when ready.")

            try:
                selected_for_ai = competitors[
                    :int(classification_limit)
                ]

                classified = (
                    classify_competitors_with_gemini(
                        business,
                        selected_for_ai,
                    )
                )

                st.session_state[
                    "classified_competitors"
                ] = classified

                st.session_state.pop(
                    "approved_competitors", None
                )

                st.success(
                    f"{len(classified)} businesses classified!"
                )
                classification_status.update(label="Competitor classification complete", state="complete", expanded=False)

            except Exception as error:
                classification_status.update(label="Classification failed. Please retry.", state="error", expanded=True)
                st.error(
                    f"AI classification failed: {error}"
                )

    # --------------------------------------
    # CLASSIFICATION RESULTS
    # --------------------------------------

    classified = st.session_state.get(
        "classified_competitors"
    )

    if classified:

        st.divider()
        st.subheader("AI Classification Results")

        direct_count = sum(
            item.get("Classification") == "Direct"
            for item in classified
        )

        indirect_count = sum(
            item.get("Classification") == "Indirect"
            for item in classified
        )

        irrelevant_count = sum(
            item.get("Classification") == "Irrelevant"
            for item in classified
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Direct", direct_count)

        with col2:
            st.metric("Indirect", indirect_count)

        with col3:
            st.metric("Irrelevant", irrelevant_count)

        classification_filter = st.multiselect(
            "Filter by Classification",
            ["Direct", "Indirect", "Irrelevant"],
            default=["Direct", "Indirect"],
            key="classification_filter",
            persist_state="session",
        )

        filtered = [
            item
            for item in classified
            if item.get("Classification")
            in classification_filter
        ]

        if filtered:
            classification_df = pd.DataFrame(filtered)

            st.dataframe(
                classification_df[
                    [
                        "Name",
                        "Distance (km)",
                        "Classification",
                        "Confidence",
                        "AI Reason",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info(
                "No competitors match this filter."
            )

    # --------------------------------------
    # COMPETITOR APPROVAL
    # --------------------------------------

    st.divider()
    st.subheader("Review and Approve Competitors")

    st.caption(
        "Select the businesses you want to include "
        "in your competitor analysis."
    )

    # Use AI results when available.
    # Otherwise allow manual approval
    # of discovered businesses.
    approval_candidates = (
        classified
        if classified
        else competitors
    )

    # Rebuild the editor from saved approvals after navigating back here.
    saved_approvals = st.session_state.get("approved_competitors")
    approved_ids = {
        competitor_id(item)
        for item in (saved_approvals or [])
    }

    approval_df = pd.DataFrame(
        [
            {
                "Approve": (
                    competitor_id(item) in approved_ids
                    if saved_approvals is not None
                    else (
                        item.get("Classification") in ("Direct", "Indirect")
                        if classified
                        else False
                    )
                ),
                "Name": item["Name"],
                "Category": item["Category"],
                "Distance (km)": item["Distance (km)"],
                "Classification": item.get(
                    "Classification",
                    "Not classified",
                ),
                "Confidence": item.get(
                    "Confidence",
                    "N/A",
                ),
            }
            for item in approval_candidates
        ]
    )

    edited_df = st.data_editor(
        approval_df,
        hide_index=True,
        width="stretch",
        disabled=[
            "Name",
            "Category",
            "Distance (km)",
            "Classification",
            "Confidence",
        ],
        column_config={
            "Approve": st.column_config.CheckboxColumn(
                "Approve",
                help="Select competitor for approval",
            ),
        },
        key="competitor_approval_editor",
    )

    if st.button(
        "Approve Selected Competitors",
        type="primary",
        key="approve_competitors_button",
    ):

        approved = []

        for index, row in edited_df.iterrows():
            if bool(row["Approve"]):
                approved.append(
                    approval_candidates[index].copy()
                )

        st.session_state[
            "approved_competitors"
        ] = approved
        st.session_state["competitor_selection_mode"] = "manual"
        st.session_state["automatic_warnings"] = []

        st.success(
            f"{len(approved)} competitors approved!"
        )

    approved = st.session_state.get(
        "approved_competitors"
    )

    if approved is not None:
        st.info(
            f"Approved Competitors: {len(approved)}"
        )

        if approved:
            render_approved_comparison(approved, business.get("name", "your business"), area_based=business.get("resolution_status") == "area_center")

    st.caption(
        "Business data © OpenStreetMap contributors. "
        "AI classifications are estimates, "
        "not verified market intelligence."
    )
    
