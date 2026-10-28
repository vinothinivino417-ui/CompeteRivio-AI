"""Confirm usable profiles without carrying a previous business's competitors."""
from services.candidate_rules import valid_coordinates, suggested_category, normalized_name, valid_industry


def saved_profile_choice(state, inputs):
    """Offer an existing location only for the same named business, for re-confirmation."""
    profile = state.get("business_profile", {})
    if not state.get("business_confirmed") or not profile.get("name") or normalized_name(profile["name"]) != normalized_name(inputs.get("name", "")):
        return None
    try:
        valid_coordinates(profile.get("latitude"), profile.get("longitude"))
    except ValueError:
        return None
    if not profile.get("location") or not valid_industry(inputs.get("category")):
        return None
    return {**profile, "industry": inputs["category"], "website": inputs.get("website", "") or profile.get("website", ""),
            "Location reuse": "Previously confirmed location; not re-geocoded. Verify the branch/address before continuing."}


def build_area_profile(entered, area):
    if not entered.get("name") or not entered.get("location"):
        raise ValueError("Enter a business name and a specific locality/address.")
    lat, lon = valid_coordinates(area.get("lat"), area.get("lon"))
    return {**entered, "location": area.get("display_name") or entered["location"],
            "latitude": lat, "longitude": lon, "osm_id": None, "osm_type": None,
            "source": "User-entered business; " + area.get("_geocoder", "OpenStreetMap") + " area geocoding",
            "resolution_status": "area_center", "coordinate_accuracy": "Approximate area centre; store location unverified"}


def confirm_business_profile(state, profile):
    lat, lon = valid_coordinates(profile.get("latitude"), profile.get("longitude"))
    if not profile.get("name") or not profile.get("location"):
        raise ValueError("Confirm a named business with an address first.")
    for key in ("competitor_search_key", "discovered_competitors", "classified_competitors", "approved_competitors",
                "ai_insights_report", "ai_insights_input", "report_generation_note", "competitor_approval_editor",
                "_google_live_ratings", "_pending_analysis", "_manual_competitor_matches", "_manual_area_profile"):
        state.pop(key, None)
    state.update({"business_profile": {**profile, "latitude": lat, "longitude": lon, "User confirmed": True},
                  "business_confirmed": True, "automatic_warnings": [], "competitor_selection_mode": "manual",
                  "competitor_category": suggested_category(profile.get("industry", ""))})
