"""One-action analysis using the existing free discovery and Gemini services."""
import json
import re
import unicodedata
import requests
from datetime import datetime, timezone
from services.candidate_rules import valid_coordinates, valid_industry, canonical_category

from dashboard.business_discovery import search_business
from dashboard.competitor_discovery import fetch_nearby_businesses, process_competitors, CATEGORY_TAGS
from services.ai_insights import classify_competitors_with_gemini, generate_competitor_insights
from services.competitor_evidence import enrich_report_inputs
from services.geocoding import find_area
from services.alternate_geocoding import find_area_alternate
from services.report_content import report_signature, build_grounded_report
from services.website_analysis import enrich_websites
from services.automatic_website_audit import enrich_automatic_audits
from services.competitor_evidence import competitor_id
from services.analysis_history import archive_current_analysis


def check_saved_websites(state, progress=None):
    business = state.get("business_profile", {})
    competitors = state.get("approved_competitors", [])
    search = state.get("competitor_search_key")
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not state.get("business_confirmed") or not competitors or not search or tuple(search[:3]) != identity:
        raise ValueError("Run an analysis for the current business first.")
    business, competitors = enrich_websites(business, competitors, progress)
    business, competitors = enrich_automatic_audits(business, competitors, progress)
    state["business_profile"], state["approved_competitors"] = business, competitors
    by_id = {competitor_id(row): row for row in competitors}
    for key in ("discovered_competitors", "classified_competitors"):
        if key in state:
            state[key] = [{**row, **({"Website analysis": by_id[competitor_id(row)]["Website analysis"]} if competitor_id(row) in by_id else {})} for row in state[key]]
    state.pop("ai_insights_report", None)
    state.pop("ai_insights_input", None)
    return business, competitors


def normalize_business_name(name):
    # D Mart, D-Mart, and DMart should compare the same way.
    return "".join(character for character in str(name).casefold() if character.isalnum())


def canonicalize_search(name, location):
    """Normalize formatting and the confirmed Chennai spelling variant only."""
    name = " ".join(unicodedata.normalize("NFKC", name).split())
    location = " ".join(unicodedata.normalize("NFKC", location).split())
    if normalize_business_name(name) == "dmart":
        name = "DMart"
    location = re.sub(r"\b(?:tamilnadu|tamildnadu)\b", "Tamil Nadu", location, flags=re.IGNORECASE)
    if re.search(r"\bchennai\b", location, flags=re.IGNORECASE):
        location = re.sub(r"\bvelacherry\b", "Velachery", location, flags=re.IGNORECASE)
    return name, location


def find_named_listing(elements, name, area_lat, area_lon):
    from dashboard.competitor_discovery import calculate_distance
    expected = normalize_business_name(name)
    matches = []
    for item in elements:
        tags = item.get("tags", {})
        names = [tags.get(key, "") for key in ("name", "brand", "official_name", "alt_name")]
        if not expected or not any(expected == normalize_business_name(value) for value in names):
            continue
        coordinates = item if item.get("lat") is not None else (item.get("center") or {})
        try:
            lat, lon = float(coordinates["lat"]), float(coordinates["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        matches.append((calculate_distance(area_lat, area_lon, lat, lon), item, lat, lon))
    return min(matches, key=lambda match: match[0]) if matches else None


def generate_saved_report(state, use_ai=True):
    profile = state.get("business_profile", {})
    search = state.get("competitor_search_key")
    identity = (str(profile.get("osm_id")), profile.get("latitude"), profile.get("longitude"))
    if not state.get("business_confirmed") or not state.get("approved_competitors") or not search or tuple(search[:3]) != identity:
        raise ValueError("Run an analysis or approve competitors for the current business first.")
    business, competitors = enrich_report_inputs(
        state["business_profile"], state["approved_competitors"], state.get("competitor_evidence", {}), state.get("scoring_weights", {})
    )
    note = ""
    if use_ai:
        try:
            report = generate_competitor_insights(business, competitors)
            if not isinstance(report, str) or not report.strip():
                raise ValueError("The AI service returned an empty report.")
        except Exception:
            note = "AI recommendations were unavailable. This factual report uses saved listings and supplied evidence, with standard validation steps instead of AI suggestions. You can retry the AI report later."
    else:
        note = "Factual report generated from saved listings and supplied evidence. No AI request was made for this report; actions are standard validation steps."
    if note:
        report = build_grounded_report(business, competitors)
        title, body = report.split("\n", 1)
        report = f"{title}\n\nReport mode: {note}\n{body}"
    state["ai_insights_report"] = report
    state["ai_insights_input"] = report_signature(business, competitors)
    state["report_generation_note"] = note
    state["automatic_warnings"] = [warning for warning in state.get("automatic_warnings", []) if not warning.startswith("Your discovered businesses are saved")]
    archive_current_analysis(state)
    return report


def resolve_automatic_profiles(name, location, category, website=""):
    """Resolve choices without discovering competitors or replacing saved work."""
    name, location = canonicalize_search(name, location)
    if not name or not location or not valid_industry(category):
        raise ValueError("Enter a business name, location, and supported industry.")
    location_service_failed = False
    try:
        matches = search_business(name, location, strict_location=True)
    except requests.RequestException:
        matches = []
        location_service_failed = True
    area_based = not bool(matches)
    if area_based:
        matches = find_area_alternate(location) if location_service_failed else find_area(location)
    profiles = []
    for match in matches[:10]:
        try:
            lat, lon = valid_coordinates(match.get("lat"), match.get("lon"))
        except ValueError:
            continue
        extra = {} if area_based else (match.get("extratags") or {})
        profiles.append({
            "name": name if area_based else (match.get("name") or name),
            "location": match.get("display_name", location), "industry": category,
            "website": website.strip() or extra.get("website") or extra.get("contact:website", ""),
            "latitude": lat, "longitude": lon, "osm_id": None if area_based else match.get("osm_id"),
            "osm_type": None if area_based else match.get("osm_type"),
            "source": "User-entered business; " + match.get("_geocoder", "OpenStreetMap") + " area geocoding" if area_based else "OpenStreetMap",
            "resolution_status": "area_center" if area_based else "business_listing",
            "coordinate_accuracy": "Approximate area centre; store location unverified" if area_based else "OpenStreetMap business listing",
            "Resolved at (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    if not profiles:
        raise ValueError("We could not locate this business or area. Include the locality, city and country, or enter a street address.")
    return profiles


def run_automatic_analysis(state, name, location, category, radius, website="", include_websites=True, progress=None, confirmed_profile=None, prepare_report=True):
    category = canonical_category(category)
    def notify(message, fraction):
        if progress:
            progress(message, fraction)
    name, location = canonicalize_search(name, location)
    if not name.strip() or not location.strip() or not valid_industry(category):
        raise ValueError("Enter a business name, location, and supported industry.")
    if not isinstance(radius, int) or not 1 <= radius <= 20:
        raise ValueError("Choose a search radius between 1 and 20 km.")
    notify("Finding your business in the requested location...", 0.05)
    business = dict(confirmed_profile) if confirmed_profile is not None else resolve_automatic_profiles(name, location, category, website)[0]
    business["industry"] = canonical_category(business.get("industry", ""))
    business["latitude"], business["longitude"] = valid_coordinates(business.get("latitude"), business.get("longitude"))
    if business.get("industry") != category or not business.get("name") or not business.get("location"):
        raise ValueError("Confirm a matching business profile before continuing.")
    business["website"] = website.strip() or business.get("website", "")
    area_based = business.get("resolution_status") == "area_center"
    notify(f"Searching for nearby {category.lower()} businesses...", 0.2)
    discovery_error = ""
    try:
        elements = fetch_nearby_businesses(business["latitude"], business["longitude"], category, radius * 1000)
    except requests.RequestException:
        if prepare_report:
            raise
        elements = []
        discovery_error = "Map discovery is temporarily unavailable. No automatic candidates were returned; add actual competitors manually or retry later."
    if area_based and confirmed_profile is None:
        named = find_named_listing(elements, name, business["latitude"], business["longitude"])
        if named:
            _, listing, lat, lon = named
            tags = listing.get("tags", {})
            business.update({"name": tags.get("name") or name.strip(), "latitude": lat, "longitude": lon,
                             "osm_id": listing.get("id"), "osm_type": listing.get("type"),
                             "source": "OpenStreetMap", "resolution_status": "business_listing",
                             "coordinate_accuracy": "OpenStreetMap business listing"})
            business["website"] = website.strip() or tags.get("website") or tags.get("contact:website", "")
            notify("Store found in the area map. Searching from its mapped location...", 0.3)
            elements = fetch_nearby_businesses(lat, lon, category, radius * 1000)
            area_based = False
    candidates = process_competitors(elements, business, category)
    for candidate in candidates:
        candidate["Distance reference"] = "Approximate area centre" if area_based else "Mapped business location"
    if not candidates and prepare_report:
        raise ValueError("No nearby businesses found. Try a larger search radius or a different industry.")
    search_key = (str(business.get("osm_id")), business["latitude"], business["longitude"], category, radius)
    # Commit the new workspace only after discovery succeeds.
    state.update({"business_profile": business, "business_confirmed": True,
                  "discovered_competitors": candidates, "competitor_search_key": search_key,
                  "competitor_category": category, "competitor_radius": radius,
                  "competitor_selection_mode": "automatic", "automatic_warnings": (
                      ["The store's exact listing was not found. This is an area-based analysis: distances are from the entered area's centre, not the store. The business location and competitor relevance need review."]
                      if area_based else []
                  )})
    if any("limited best matches" in row.get("Discovery source", "") for row in candidates):
        state["automatic_warnings"].append("Overpass was unavailable. Discovery used a limited nearby best-match search; the list is not exhaustive.")
    for key in ("classified_competitors", "approved_competitors", "ai_insights_report", "ai_insights_input", "competitor_approval_editor"):
        state.pop(key, None)
    if not candidates:
        state["approved_competitors"] = []
        state["competitor_selection_mode"] = "pending_review"
        custom_note = "This custom industry has no automatic map category. Add actual competitors manually; no unrelated category was substituted." if category not in CATEGORY_TAGS else ""
        state["automatic_warnings"].append(discovery_error or custom_note or "No mapped competitors found in this category and radius. This does not mean there are no competitors. Add actual businesses manually or try a larger radius.")
        notify("Review the location and add competitors, or retry discovery.", 1.0)
        return []
    shortlist = candidates[:15]
    if include_websites:
        notify("Checking available public websites (unavailable sites will be skipped)...", 0.38)
        business, shortlist = enrich_websites(business, shortlist, lambda message: notify(message, 0.4))
        state["business_profile"] = business
        state["discovered_competitors"] = shortlist + candidates[15:]
    notify(f"Classifying {len(shortlist)} nearby candidates with Gemini...", 0.5)
    try:
        classified = classify_competitors_with_gemini(business, shortlist)
        if len(classified) != len(shortlist):
            raise ValueError("Classification did not cover every candidate.")
        state["classified_competitors"] = classified
        selected = [row for row in classified if row.get("Classification") in ("Direct", "Indirect")]
        if not selected:
            # Keep the classifications; label these as provisional, not confirmed competitors.
            selected = classified
            state["automatic_warnings"].append("No direct or indirect competitors were supported by the available evidence. The report includes nearby candidates for review; their competitive relevance is unverified.")
    except Exception:
        selected = shortlist
        state["automatic_warnings"].append("AI classification was unavailable. Nearby candidates are not classified and their competitive relevance is unverified. Review the list in Competitor Analysis; a factual report can still be prepared.")
    state["approved_competitors"] = [
        {**row, "Selection": "Automatically selected; user review recommended"} for row in selected
    ]
    if include_websites:
        business, selected_audits = enrich_automatic_audits(
            business, state["approved_competitors"], lambda message: notify(message, 0.7))
        state["business_profile"] = business
        state["approved_competitors"] = selected_audits
    if not prepare_report:
        state["competitor_selection_mode"] = "pending_review"
        notify("Candidates ready. Review and approve your competitor selection.", 1.0)
        return state["approved_competitors"]
    notify("Preparing the report from selected businesses and any saved evidence...", 0.8)
    try:
        generate_saved_report(state)
    except Exception as error:
        state["automatic_warnings"].append(f"Your discovered businesses are saved, but the AI report could not finish. Use Retry report below. Details: {error}")
    notify("Analysis finished", 1.0)
    return state["approved_competitors"]
