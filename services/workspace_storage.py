"""Save the local dashboard workspace without storing widget internals or secrets."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


WORKSPACE_PATH = Path(__file__).resolve().parents[1] / ".local" / "workspace.json"
SAVED_TYPES = {
    "website_audits": dict,
    "report_generation_note": str,
    "scoring_weights": dict,
    "analysis_history": list,
    "analysis_history_warning": str,
    "automatic_inputs": dict,
    "automatic_warnings": list,
    "competitor_selection_mode": str,
    "competitor_evidence": dict,
    "business_confirmed": bool,
    "business_profile": dict,
    "business_search_results": list,
    "business_search_input": dict,
    "discovered_competitors": list,
    "classified_competitors": list,
    "approved_competitors": list,
    "competitor_search_key": (list, tuple),
    "competitor_category": str,
    "competitor_radius": int,
    "competitor_classification_limit": int,
    "classification_filter": list,
    "ai_insights_report": str,
    "ai_insights_input": str,
    "appearance_mode": str,
}


def snapshot(state):
    return {
        key: state[key] for key, expected in SAVED_TYPES.items()
        if key in state and isinstance(state[key], expected)
    }


def read_workspace(path=WORKSPACE_PATH):
    path = Path(path)
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Unsupported saved workspace format")
    data = document.get("state")
    if not isinstance(data, dict):
        raise ValueError("Saved workspace is missing its state")
    restored = {}
    for key, value in data.items():
        if key not in SAVED_TYPES:
            continue
        if not isinstance(value, SAVED_TYPES[key]):
            raise ValueError(f"Invalid saved value for {key}")
        if key == "competitor_search_key":
            if len(value) != 5:
                raise ValueError("Invalid saved competitor search")
            value = tuple(value)
        if key in ("discovered_competitors", "classified_competitors", "approved_competitors", "business_search_results", "analysis_history"):
            if not all(isinstance(row, dict) for row in value):
                raise ValueError(f"Invalid saved rows for {key}")
        restored[key] = value
    return restored


def write_workspace(state, path=WORKSPACE_PATH):
    path = Path(path)
    # Serialize before touching the old file. A failed write preserves the last save.
    payload = json.dumps({"version": 1, "state": snapshot(state)}, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


@contextmanager
def persistent_workspace(state, on_error, path=WORKSPACE_PATH):
    if not state.get("_workspace_loaded"):
        try:
            saved = read_workspace(path)
            # Preserve current session data when this feature is first hot-reloaded.
            for key, value in saved.items():
                state.setdefault(key, value)
            state["_workspace_saved"] = json.dumps(saved, sort_keys=True)
        except (OSError, ValueError, TypeError) as error:
            state["_workspace_storage_error"] = f"Could not restore saved work: {error}. Your saved file has been preserved."
        state["_workspace_loaded"] = True

    if state.get("_workspace_storage_error"):
        on_error(state["_workspace_storage_error"])
    try:
        yield
    finally:
        # Also runs when Streamlit stops or reruns after confirming a business.
        if not state.get("_workspace_storage_error"):
            try:
                data = snapshot(state)
                serialized = json.dumps(data, sort_keys=True)
                if serialized != state.get("_workspace_saved"):
                    write_workspace(data, path)
                    state["_workspace_saved"] = serialized
            except (OSError, ValueError, TypeError) as error:
                on_error(f"Could not save your latest changes locally: {error}")
