
import streamlit as st
import pandas as pd
from dashboard.business_discovery import render_business_discovery

from dashboard.theme import apply_theme
from dashboard.navigation import sidebar_navigation, PAGE_LABELS
from services.automatic_analysis import generate_saved_report
from services.report_export import create_pdf_report
from dashboard.competitor_discovery import render_competitor_discovery
from dashboard.overview import render_overview
from services.workspace_storage import persistent_workspace
from services.competitor_evidence import enrich_report_inputs
from dashboard.evidence import render_evidence
from dashboard.automatic_analysis import render_automatic_analysis
from dashboard.keywords import render_keywords
from dashboard.marketing import render_marketing
from dashboard.history import render_history
from services.analysis_history import current_snapshot
from dashboard.analysis_bundle import render_bundle_download
from services.report_content import report_signature


st.set_page_config(
    page_title="CompeteRivio AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

with persistent_workspace(st.session_state, st.warning):
    page, mode = sidebar_navigation()
    apply_theme(mode)

    # Apply matching text colors to all Plotly charts
    import plotly.io as pio

    pio.templates.default = "streamlit"

    st.title(PAGE_LABELS.get(page, page))


    if page == "Automatic Analysis":
        render_automatic_analysis()

    elif page == "Overview":
        render_overview()

    elif page == "Business & Discovery":
        render_business_discovery()

    elif page == "Competitor Analysis":
        render_competitor_discovery()

    elif page == "Evidence & Scores":
        render_evidence()

    elif page == "Keyword Intelligence":
        render_keywords()

    elif page == "Marketing Intelligence":
        render_marketing()

    elif page == "Analysis History":
        render_history()

    elif page == "AI Insights & Reports":
        st.subheader("Gemini AI Competitive Insights")
        st.caption(
            "AI analysis of your confirmed business and approved competitors. "
            "Classifications are AI estimates. Review before making decisions."
        )

        business_data = st.session_state.get("business_profile", {})
        competitor_data = st.session_state.get("approved_competitors", [])

        if not st.session_state.get("business_confirmed") or not business_data:
            st.info("Confirm your business in Business & Discovery first.")
            st.stop()

        search_key = st.session_state.get("competitor_search_key")
        business_key = (
            str(business_data.get("osm_id")),
            business_data.get("latitude"),
            business_data.get("longitude"),
        )
        if not competitor_data or not search_key or tuple(search_key[:3]) != business_key:
            st.info("Discover and approve competitors for this business in Competitor Analysis first.")
            st.stop()

        st.success(f"Business: {business_data.get('name', 'Your business')} | {len(competitor_data)} approved competitors")
        with st.expander("Review competitors included in this report"):
            st.dataframe(pd.DataFrame(competitor_data), hide_index=True, width="stretch")

        # Reports belong to the exact business and selection used to generate them.
        business_data, competitor_data = enrich_report_inputs(
            business_data, competitor_data, st.session_state.get("competitor_evidence", {}), st.session_state.get("scoring_weights", {})
        )
        report_input = report_signature(business_data, competitor_data)
        if st.session_state.get("ai_insights_input") != report_input:
            st.session_state.pop("ai_insights_report", None)

        if st.button("Generate AI Insights", type="primary"):
            with st.status("Generating AI insights... Please wait.", expanded=True) as insights_status:
                st.write("Gemini is preparing your report. It will appear below when ready.")
                try:
                    generate_saved_report(st.session_state)
                    insights_status.update(label="Factual report ready" if st.session_state.get("report_generation_note") else "AI insights ready", state="complete", expanded=False)
                except Exception as error:
                    insights_status.update(label="AI analysis failed. Please retry.", state="error", expanded=True)
                    st.error(f"AI analysis failed: {error}")

        if "ai_insights_report" in st.session_state:
            if warning := st.session_state.get("analysis_history_warning"):
                st.warning(warning)
            report = st.session_state["ai_insights_report"]
            if note := st.session_state.get("report_generation_note"):
                st.info(note)
            st.markdown(report)

            # Markdown Download
            st.download_button(
                "Download AI Insights",
                data=report,
                file_name="CompeteRivio_AI_Insights.md",
                mime="text/markdown",
            )

            # PDF Download
            pdf_bytes = create_pdf_report(report)
            st.download_button(
                "Download PDF Report",
                data=pdf_bytes,
                file_name="CompeteRivio_AI_Report.pdf",
                mime="application/pdf",
            )
            render_bundle_download(current_snapshot(st.session_state), pdf_bytes, "reports_analysis_bundle")

    else:
        st.info("This page is under development.")
