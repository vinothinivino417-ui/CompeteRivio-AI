"""Reuse search details without running discovery or replacing current results."""
import uuid
from services.candidate_rules import valid_industry


def saved_search_inputs(snapshot, categories):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("business"), dict):
        raise ValueError("This saved run has no usable business details.")
    business = snapshot["business"]
    name, location = business.get("name"), business.get("location")
    if not all(isinstance(value, str) and value.strip() for value in (name, location)):
        raise ValueError("The saved business needs a name and location before its search can be reused.")
    category, radius = snapshot.get("category"), snapshot.get("radius_km")
    if not valid_industry(category):
        raise ValueError("This saved industry is unavailable. Enter the search manually in Automatic Analysis.")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not 1 <= radius <= 20 or radius != int(radius):
        raise ValueError("The saved radius must be a whole number from 1 to 20 km. Enter the search manually instead.")
    website = business.get("website", "") or ""
    if not isinstance(website, str):
        raise ValueError("The saved website field is invalid. Enter the search manually instead.")
    return {"name": name.strip(), "location": location.strip(), "category": category,
            "radius": int(radius), "website": website.strip(), "include_websites": True}


def stage_saved_search(state, snapshot, categories):
    inputs = saved_search_inputs(snapshot, categories)
    state["automatic_inputs"] = inputs
    # A new widget identity replaces an older draft, even if the form was visited.
    state["_automatic_form_revision"] = uuid.uuid4().hex
    state["_saved_search_notice"] = f"Search details loaded for {inputs['name']}. Review the name, branch address and settings, then click Find business profile. Your existing results remain below until a new search runs."
    state["main_navigation"] = "Automatic Analysis"
    return inputs
