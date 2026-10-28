import hashlib
import json
import streamlit as st

from services.competitor_evidence import DEFAULT_WEIGHTS, WEIGHT_PRESETS, CATEGORIES, evidence_scope, validate_weights, weights_for_business


def render_scoring_weights(business):
    scope = evidence_scope(business)
    saved = st.session_state.get("scoring_weights", {})
    try:
        current = weights_for_business(business, saved)
    except ValueError:
        st.warning("Saved scoring weights are invalid. Apply a preset below to reset them.")
        current = dict(DEFAULT_WEIGHTS)
    st.subheader("Scoring priorities")
    st.caption("These are relative weights. Scores use only complete, comparable categories and normalize the included weights automatically. Presets are starting choices, not validated industry benchmarks.")
    applied_name = next((name for name, weights in WEIGHT_PRESETS.items() if weights == current), "Custom")
    st.write(f"Currently applied: **{applied_name}**")
    scope_key = hashlib.sha256(scope.encode()).hexdigest()[:12]
    pending = st.session_state.pop(f"_next_scoring_preset_{scope_key}", None)
    if pending:
        st.session_state[f"scoring_preset_{scope_key}"] = pending
    notice = st.session_state.pop("_scoring_notice", None)
    if notice:
        st.success(notice)
    preset_names = list(WEIGHT_PRESETS) + ["Custom"]
    preset_key = f"scoring_preset_{scope_key}"
    preset = st.selectbox("Scoring preset", preset_names, index=None if preset_key in st.session_state else preset_names.index(applied_name), key=preset_key, persist_state="session")
    defaults = current if preset == "Custom" else WEIGHT_PRESETS[preset]
    version = hashlib.sha256(json.dumps([scope, preset, defaults], sort_keys=True).encode()).hexdigest()[:12]
    with st.form("scoring_weights_form"):
        selected = {}
        for index, (category, value) in enumerate(defaults.items()):
            label = category if category in CATEGORIES else f"{category} (data unavailable)"
            selected[category] = st.slider(label, 0, 100, int(round(value)), key=f"score_weight_{version}_{index}")
        apply = st.form_submit_button("Apply scoring weights", type="primary")
    if apply:
        try:
            current = validate_weights(selected)
            st.session_state["scoring_weights"] = {**saved, scope: current}
            st.session_state.pop("ai_insights_report", None)
            st.session_state.pop("ai_insights_input", None)
            st.session_state[f"_next_scoring_preset_{scope_key}"] = next((name for name, weights in WEIGHT_PRESETS.items() if weights == current), "Custom")
            st.session_state["_scoring_notice"] = "Weights saved for this business. Scores updated; regenerate the report to use these priorities."
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    return current
