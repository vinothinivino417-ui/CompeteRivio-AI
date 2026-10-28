from services.competitor_evidence import enrich_report_inputs
from services.report_content import report_signature


def make_state():
    business = {"name": "DMart", "location": "Velachery, Chennai", "osm_id": 1, "latitude": 13, "longitude": 80}
    rows = [{"Name": "Market A", "Category": "Supermarket", "Distance (km)": 0.1,
             "Classification": "Direct", "Confidence": "Medium", "OSM ID": "2", "OSM Type": "node"}]
    state = {"business_confirmed": True, "business_profile": business, "approved_competitors": rows,
             "discovered_competitors": rows, "competitor_search_key": ("1", 13, 80, "Supermarket", 3),
             "ai_insights_report": "# DMart report\n\n## Evidence\n\nOne selected nearby business.", "competitor_evidence": {}}
    sign_state(state)
    return state


def sign_state(state):
    business, rows = enrich_report_inputs(state["business_profile"], state["approved_competitors"], state.get("competitor_evidence", {}), state.get("scoring_weights", {}))
    state["ai_insights_input"] = report_signature(business, rows)
