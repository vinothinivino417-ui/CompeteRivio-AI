from datetime import datetime, timedelta, timezone
import json
import pandas as pd
import streamlit as st

from services.analysis_history import archive_current_analysis, current_snapshot, history_record, remove_history_record, MAX_HISTORY
from services.report_export import create_pdf_report
from services.history_comparison import compare_saved_runs
from services.competitor_evidence import evidence_scope
from services.history_backup import prepare_history_restore, restore_history
from dashboard.analysis_bundle import render_bundle_download
from services.saved_search import saved_search_inputs, stage_saved_search
from dashboard.competitor_discovery import CATEGORY_TAGS


def local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %H:%M:%S IST")
    except (ValueError, TypeError):
        return "Unknown save time"


def render_history():
    st.caption("Choose a saved report to read, download, or search again. Opening it uses no tokens.")
    if error := st.session_state.pop("_saved_search_error", None):
        st.error(error)
    render_history_restore()
    if st.button("Save current report to history", disabled=current_snapshot(st.session_state) is None, key="save_current_to_history"):
        record = archive_current_analysis(st.session_state)
        if record:
            st.success("Current report is saved. Identical reports are not duplicated.")
    if warning := st.session_state.get("analysis_history_warning"):
        st.warning(warning)
    history = list(reversed(st.session_state.get("analysis_history", [])))
    if not history:
        st.info("No saved analyses yet. Generate a report in Automatic Analysis or AI Insights & Reports. If a current report is already available, use Save current report to history above.")
        return
    st.caption(f"{len(history)} / {MAX_HISTORY} saved runs. Older runs are never silently deleted. This is a report archive, not a time series of new market measurements.")
    summaries, labels = [], {}
    for index, record in enumerate(history, 1):
        snapshot = record.get("snapshot", {})
        business = snapshot.get("business", {})
        labels[record["id"]] = f"{business.get('name', 'Business')} | {local_time(record.get('created_at'))} | Saved run {index}"
        summaries.append({"Business": business.get("name", "Business"), "Saved at": local_time(record.get("created_at")),
                          "Industry": snapshot.get("category"), "Radius (km)": snapshot.get("radius_km"),
                          "Selected competitors": len(snapshot.get("competitors", []))})
    with st.expander("All saved runs"):
        st.dataframe(pd.DataFrame(summaries), hide_index=True, width="stretch")
    options = [record["id"] for record in history]
    if st.session_state.get("history_selected_run") not in options:
        st.session_state.pop("history_selected_run", None)
    selected = st.selectbox("Open saved analysis", options, format_func=labels.get, key="history_selected_run", persist_state="session")
    try:
        record = history_record(st.session_state, selected)
    except ValueError as error:
        st.error(str(error))
        return
    snapshot = record["snapshot"]
    render_saved_comparison(record, history, labels)
    business = snapshot["business"]
    st.subheader(business.get("name", "Saved business"))
    st.write(business.get("location", "Location unavailable"))
    st.caption(f"Report saved: {local_time(record['created_at'])}. Website retrieval times and manual observation dates remain in the evidence. Opening this record does not replace your current workspace.")
    render_reuse_search(snapshot)
    with st.expander("Saved competitor list"):
        frame = pd.DataFrame(snapshot["competitors"]).reindex(columns=["Name", "Category", "Distance (km)", "Classification", "Confidence", "Discovery source", "Website"])
        st.dataframe(frame, hide_index=True, width="stretch")
    with st.expander("Preview saved report"):
        st.markdown(snapshot["report"])
    suffix = record["id"][:8]
    pdf_bytes = create_pdf_report(snapshot["report"])
    st.download_button("Download saved PDF", pdf_bytes, f"CompeteRivio_Saved_Report_{suffix}.pdf", "application/pdf", key="history_pdf")
    export = [{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()} for row in snapshot["competitors"]]
    with st.expander("More download formats"):
        render_bundle_download(snapshot, pdf_bytes, "history_analysis_bundle", record)
        st.download_button("Download saved report text", snapshot["report"], f"CompeteRivio_Saved_Report_{suffix}.md", "text/markdown", key="history_markdown")
        st.download_button("Download saved competitors (CSV)", pd.DataFrame(export).to_csv(index=False).encode("utf-8-sig"), f"CompeteRivio_Saved_Competitors_{suffix}.csv", "text/csv", key="history_csv")
    with st.expander("Back up or manage local history"):
        st.download_button("Download complete history backup (JSON)", json.dumps({"schema_version": 1, "analyses": history}, ensure_ascii=False, indent=2), "CompeteRivio_Analysis_History.json", "application/json", key="history_backup")
        st.caption("Removing a saved run deletes only that archive entry. Your current workspace and files you already downloaded are unchanged.")
        if st.button("Remove selected saved run", key="remove_history_run"):
            remove_history_record(st.session_state, selected)
            st.rerun()


def render_saved_comparison(baseline, history, labels):
    matches = [item["id"] for item in history if item["id"] != baseline["id"]
               and evidence_scope(item.get("snapshot", {}).get("business", {})) == evidence_scope(baseline["snapshot"]["business"])]
    with st.expander("Compare saved selections"):
        st.caption("The opened run is the baseline. Changes describe saved selections, not businesses opening or closing. Different search settings or manual choices can change the list. Saved dates are report dates, not new measurement dates.")
        if not matches:
            st.info("Save another analysis for this same business and mapped location to compare selections.")
            return
        if st.session_state.get("history_comparison_run") not in matches:
            st.session_state.pop("history_comparison_run", None)
        selected = st.selectbox("Compare baseline with", matches, format_func=labels.get, key="history_comparison_run", persist_state="session")
        try:
            other = history_record(st.session_state, selected)
            result = compare_saved_runs(baseline, other)
        except ValueError as error:
            st.warning(str(error))
            return
        st.write(f"Baseline: {local_time(baseline.get('created_at'))}. Comparison: {local_time(other.get('created_at'))}.")
        columns = st.columns(3)
        for column, label, key in zip(columns, ["Added to selection", "Removed from selection", "Kept in selection"], ["added", "removed", "retained"]):
            column.metric(label, result[key])
        st.dataframe(pd.DataFrame(result["settings"]).fillna("Unavailable").astype(str), hide_index=True, width="stretch")
        frame = pd.DataFrame(result["competitors"])
        st.dataframe(frame, hide_index=True, width="stretch")
        st.caption("Competitors match by saved OSM identifier where available. Missing identifiers use the saved name and coordinates; renamed listings may appear as different selections. Relative scores are not compared because weights, evidence, and the comparison group can change.")
        st.download_button("Download selection comparison (CSV)", frame.to_csv(index=False).encode("utf-8-sig"), "CompeteRivio_Selection_Comparison.csv", "text/csv", key="history_comparison_csv")


def render_history_restore():
    if notice := st.session_state.pop("_history_restore_notice", None):
        st.success(notice)
    with st.expander("Restore a history backup"):
        st.caption("Upload the JSON file from Download complete history backup. Preview the merge, then restore. Existing runs are kept and duplicate report snapshots are skipped. Restored reports retain their original content and save dates; their evidence is not refreshed or independently verified.")
        uploaded = st.file_uploader("Choose history backup (JSON, up to 20 MB)", type="json", max_upload_size=20, key="history_restore_file")
        if uploaded is None:
            return
        try:
            payload = uploaded.getvalue()
            preview = prepare_history_restore(st.session_state, payload)
        except ValueError as error:
            st.error(str(error))
            return
        st.write(f"Ready to add {preview['added']} saved run(s); skip {preview['duplicates']} duplicate(s).")
        if st.button("Restore saved reports", disabled=not preview["added"], key="restore_history_backup"):
            try:
                result = restore_history(st.session_state, payload)
                st.session_state["_history_restore_notice"] = f"Restored {result['added']} saved run(s). Skipped {result['duplicates']} duplicate(s). Your current analysis is unchanged."
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def _reuse_saved_search(snapshot):
    try:
        stage_saved_search(st.session_state, snapshot, CATEGORY_TAGS)
    except ValueError as error:
        st.session_state["_saved_search_error"] = str(error)


def render_reuse_search(snapshot):
    try:
        saved_search_inputs(snapshot, CATEGORY_TAGS)
    except ValueError as error:
        st.caption(f"Saved search cannot be reused: {error}")
        return
    st.button("Use this saved search", on_click=_reuse_saved_search, args=(snapshot,), key="reuse_history_search")
    st.caption("Fills the Automatic Analysis form with the saved mapped name/address, industry, radius and website. Website checks default to on. Review the form before searching; loading it uses no API calls or tokens.")
