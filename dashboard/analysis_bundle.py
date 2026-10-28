import streamlit as st
from services.analysis_bundle import create_analysis_bundle


def render_bundle_download(snapshot, pdf_bytes, key, saved_record=None):
    if snapshot is None:
        return
    try:
        data = create_analysis_bundle(snapshot, pdf_bytes, saved_record)
    except (ValueError, TypeError) as error:
        st.warning(f"Complete download could not be prepared: {error}")
        return
    st.download_button("Download complete analysis (ZIP)", data, "CompeteRivio_Complete_Analysis.zip", "application/zip", key=key)
    st.caption("Includes PDF, report text, competitor and evidence CSVs, captured keyword sources, and a restorable history snapshot. Uses saved evidence; no extra API calls.")
