"""Local, immutable report snapshots. Viewing history never calls external APIs."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import uuid

from services.competitor_evidence import enrich_report_inputs
from services.report_content import REPORT_VERSION, report_signature


MAX_HISTORY = 50


def current_snapshot(state):
    business = state.get("business_profile", {})
    competitors = state.get("approved_competitors", [])
    search = state.get("competitor_search_key")
    report = state.get("ai_insights_report")
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not state.get("business_confirmed") or not competitors or not search or len(search) != 5 or tuple(search[:3]) != identity:
        return None
    if not isinstance(report, str) or not report.strip():
        return None
    business, competitors = enrich_report_inputs(business, competitors, state.get("competitor_evidence", {}), state.get("scoring_weights", {}))
    if state.get("ai_insights_input") != report_signature(business, competitors):
        return None
    return copy.deepcopy({"business": business, "competitors": competitors,
                          "category": search[3], "radius_km": search[4],
                          "discovered_count": len(state.get("discovered_competitors", []) or []),
                          "selection_mode": state.get("competitor_selection_mode", "manual"),
                          "report": report, "report_version": REPORT_VERSION})


def archive_current_analysis(state):
    snapshot = current_snapshot(state)
    if snapshot is None:
        state["analysis_history_warning"] = "Generate a report for your current business and selection before saving it to history."
        return None
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    history = state.get("analysis_history", [])
    for record in history:
        if record.get("fingerprint") == fingerprint:
            state.pop("analysis_history_warning", None)
            return copy.deepcopy(record)
    if len(history) >= MAX_HISTORY:
        state["analysis_history_warning"] = "History has reached 50 saved analyses. Your current report is ready, but was not archived. Download a history backup and remove an old saved run in Analysis History to make space."
        return None
    record = {"id": uuid.uuid4().hex, "schema_version": 1,
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "fingerprint": fingerprint, "snapshot": snapshot}
    state["analysis_history"] = history + [record]
    state.pop("analysis_history_warning", None)
    return copy.deepcopy(record)


def history_record(state, record_id):
    for record in state.get("analysis_history", []):
        if record.get("id") == record_id:
            snapshot = record.get("snapshot")
            if record.get("schema_version") != 1 or not isinstance(snapshot, dict):
                raise ValueError("Unsupported saved analysis format.")
            if not isinstance(snapshot.get("business"), dict) or not isinstance(snapshot.get("competitors"), list) or not all(isinstance(item, dict) for item in snapshot["competitors"]) or not isinstance(snapshot.get("report"), str):
                raise ValueError("This saved analysis is incomplete.")
            return copy.deepcopy(record)
    raise ValueError("The selected saved analysis could not be found.")


def remove_history_record(state, record_id):
    history = state.get("analysis_history", [])
    remaining = [record for record in history if record.get("id") != record_id]
    if len(remaining) == len(history):
        return False
    state["analysis_history"] = remaining
    state.pop("analysis_history_warning", None)
    return True
