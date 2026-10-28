"""Validated user overrides scoped to the currently confirmed business search."""
from datetime import datetime, timezone
import math
from urllib.parse import urlsplit

from services.candidate_rules import CATEGORY_TAGS, is_directory, normalized_name, valid_coordinates, valid_industry, relevance_fields, ranked
from services.competitor_evidence import competitor_id


def distance_km(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    value = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(other_lon-lon)/2)**2
    return 12742 * math.asin(min(1, math.sqrt(max(0, value))))


def _current(state):
    business = state.get("business_profile", {})
    search = state.get("competitor_search_key")
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not state.get("business_confirmed") or not search or tuple(search[:3]) != identity:
        raise ValueError("Run a search for the confirmed business before editing competitors.")
    return business, search


def invalidate_report(state):
    for key in ("ai_insights_report", "ai_insights_input", "report_generation_note", "competitor_approval_editor", "_google_live_ratings"):
        state.pop(key, None)
    if state.get("competitor_selection_mode") != "pending_review":
        state["competitor_selection_mode"] = "manual"


def add_competitor(state, name, category, latitude, longitude, address, website="", osm_id=None, osm_type=None, tags=None):
    business, search = _current(state)
    name, address, website = str(name).strip(), str(address).strip(), str(website).strip()
    if not name or not address or not valid_industry(category):
        raise ValueError("Enter a competitor name, address and supported category.")
    lat, lon = valid_coordinates(latitude, longitude)
    if website:
        parsed = urlsplit(website)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use an HTTP(S) website without credentials, or leave it blank.")
    if is_directory(name, website, tags):
        raise ValueError("This looks like a directory or aggregator. Add the actual business instead.")
    if osm_id is not None and str(osm_id) == str(business.get("osm_id")) and osm_type == business.get("osm_type"):
        raise ValueError("The confirmed business cannot be its own competitor.")
    distance = distance_km(business["latitude"], business["longitude"], lat, lon)
    if normalized_name(name) == normalized_name(business.get("name")) and distance < .05:
        raise ValueError("This matches the confirmed business at the same location.")
    current = state.get("discovered_competitors", [])
    for row in current:
        same_id = osm_id is not None and str(osm_id) == str(row.get("OSM ID")) and osm_type == row.get("OSM Type")
        if same_id or (normalized_name(name) == normalized_name(row["Name"]) and distance_km(lat, lon, row["Latitude"], row["Longitude"]) < .05):
            if any(competitor_id(row) == competitor_id(selected) for selected in state.get("approved_competitors", [])):
                raise ValueError("This competitor is already selected.")
            state["approved_competitors"] = state.get("approved_competitors", []) + [dict(row)]
            invalidate_report(state)
            return row
    observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {"Name": name, "Category": category, "Website": website, "Address": address,
           "Latitude": lat, "Longitude": lon, "Distance (km)": round(distance, 2),
           "Classification": "Not classified", "Confidence": "N/A", "AI Reason": "User-added candidate; competitive relevance needs review.",
           "Discovery source": "User-confirmed OpenStreetMap lookup" if osm_id is not None else "User-entered business and coordinates (unverified)",
           "Added at (UTC)": observed, "Selection": "User added",
           "Outside search radius": distance > search[4],
           **relevance_fields(tags or {}, search[3], distance)}
    if osm_id is not None:
        row.update({"OSM ID": str(osm_id), "OSM Type": osm_type})
    else:
        row.update({"OSM ID": None, "OSM Type": ""})
    state["discovered_competitors"] = ranked(current + [row])
    if "classified_competitors" in state:
        state["classified_competitors"] = ranked(state["classified_competitors"] + [row])
    state["approved_competitors"] = state.get("approved_competitors", []) + [row]
    invalidate_report(state)
    return row


def remove_competitor(state, target_id):
    _current(state)
    current = state.get("approved_competitors", [])
    updated = [row for row in current if competitor_id(row) != target_id]
    if len(updated) == len(current):
        raise ValueError("Select a current competitor to remove.")
    state["approved_competitors"] = updated
    invalidate_report(state)
