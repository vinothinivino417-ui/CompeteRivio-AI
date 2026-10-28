import json
from uuid import uuid4
import streamlit as st
import pandas as pd
import hashlib
import requests

from dashboard.competitor_discovery import CATEGORY_TAGS
from dashboard.navigation import navigate_to, review_analysis_step
from services.automatic_analysis import run_automatic_analysis, generate_saved_report, canonicalize_search, resolve_automatic_profiles
from services.report_export import create_pdf_report
from services.competitor_evidence import enrich_report_inputs
from services.report_content import report_signature
from dashboard.website_analysis import render_website_checks
from dashboard.evidence_review import render_evidence_review
from dashboard.analysis_bundle import render_bundle_download
from services.analysis_history import current_snapshot
from dashboard.industry_picker import industry_picker
from services.business_profiles import saved_profile_choice


def clear_analysis_inputs():
    """Start a blank form without deleting the last analysis or saved reports."""
    st.session_state["automatic_inputs"] = {}
    st.session_state["_automatic_form_revision"] = uuid4().hex
    st.session_state.pop("_saved_search_notice", None)
    st.session_state.pop("_pending_analysis", None)
    st.session_state.pop("_profile_lookup_failure", None)
    st.session_state.pop("_analysis_review_step", None)


def render_automatic_analysis():
    step = st.session_state.get("_analysis_review_step")
    if step == "competitors":
        st.caption("03 · REVIEW COMPETITORS")
        st.button("Back", icon=":material/arrow_back:", on_click=review_analysis_step,
                  args=("profile",), key="review_back_profile", help="Return to the confirmed business profile.")
        _render_competitor_review()
        st.button("Forward to dashboard", on_click=navigate_to, args=("Overview",), key="review_forward_dashboard")
        return
    if step == "profile":
        st.caption("02 · CONFIRMED PROFILE")
        st.button("Back", icon=":material/arrow_back:", on_click=review_analysis_step,
                  args=("details",), key="profile_back_details", help="Return to the business input details.")
        profile = st.session_state.get("business_profile", {})
        st.subheader(profile.get("name", "Your business"))
        st.write(profile.get("location", ""))
        st.write("Industry:", profile.get("industry", ""))
        st.write("Website:", profile.get("website") or "Not supplied")
        if profile.get("resolution_status") == "area_center":
            st.warning("Approximate area centre; the exact store location is unverified.")
        st.button("Continue to competitors", on_click=review_analysis_step, key="profile_forward_competitors")
        return
    st.caption("01 · BUSINESS DETAILS     →     02 · CONFIRM PROFILE     →     03 · ANALYSIS & DASHBOARD")
    st.subheader("Start with your business")
    st.write("One search brings nearby businesses, comparisons, and your report together.")
    st.button("Clear inputs", key="auto_clear_inputs", on_click=clear_analysis_inputs,
              help="Clear the form to enter another shop. Your previous results and saved reports stay available.")
    if notice := st.session_state.pop("_saved_search_notice", None):
        st.info(notice)
    saved = st.session_state.get("automatic_inputs", {})
    revision = st.session_state.get("_automatic_form_revision", "default")
    with st.form(f"automatic_analysis_form_{revision}"):
        categories = list(CATEGORY_TAGS)
        business_column, industry_column = st.columns([2,1])
        with business_column:
            name = st.text_input("Business name", value=saved.get("name", ""), placeholder="e.g. DMart", key=f"auto_name_{revision}")
        with industry_column:
            category = industry_picker("Industry — select or type your own", f"auto_category_{revision}", saved.get("category"))
        location = st.text_input("Location", value=saved.get("location", ""), placeholder="e.g. Velachery, Chennai, India", key=f"auto_location_{revision}")
        with st.expander("Optional search settings"):
            radius = st.slider("Search radius (km)", 1, 20, value=saved.get("radius", 3), key=f"auto_radius_{revision}")
            website = st.text_input("Website (optional)", value=saved.get("website", ""), key=f"auto_website_{revision}")
            include_websites = st.checkbox("Include free website checks", value=saved.get("include_websites", True), key=f"auto_websites_{revision}")
            st.caption("Extracts terms from accessible listed/supplied websites and attempts mobile quality audits for up to two sites using Google PageSpeed. URLs are sent to Google; quotas may limit audits. No API key required.")
        submitted = st.form_submit_button("Find business profile", type="primary", width="stretch")
    st.caption("Example: DMart · Velachery, Chennai, India · Supermarket. Search availability and AI quotas may affect results.")
    if submitted:
        st.session_state.pop("_analysis_review_step", None)
        search_name, search_location = canonicalize_search(name, location)
        if (search_name, search_location) != (name, location):
            st.info(f"Searching with corrected formatting/spelling: {search_name} — {search_location}")
        inputs = dict(name=search_name, location=search_location, category=category, radius=radius, website=website, include_websites=include_websites)
        st.session_state["automatic_inputs"] = inputs
        st.session_state.pop("_pending_analysis", None)
        st.session_state.pop("_profile_lookup_failure", None)
        try:
            with st.spinner("Finding business profiles..."):
                profiles = resolve_automatic_profiles(search_name, search_location, category, website)
            st.session_state["_pending_analysis"] = {"inputs": inputs, "profiles": profiles, "revision": uuid4().hex}
        except requests.RequestException as error:
            st.session_state["_profile_lookup_failure"] = {"inputs": inputs}
            st.warning("The location service did not respond. Your saved location and previous results have been kept. Retry later, or re-confirm a saved location below if it is the correct branch.")
            with st.expander("Location service details"):
                st.text(str(error))
        except (ValueError, OSError) as error:
            st.session_state["_profile_lookup_failure"] = {"inputs": inputs}
            st.error(str(error))

    failure = st.session_state.get("_profile_lookup_failure")
    if failure:
        saved_profile = saved_profile_choice(st.session_state, failure["inputs"])
        if saved_profile:
            st.write("**Previously confirmed location:**", saved_profile["location"])
            st.caption("Use this only if it is the branch/area you want. It is saved data, not a fresh lookup.")
            if st.button("Use saved location for this business", key="reuse_saved_profile"):
                st.session_state["_pending_analysis"] = {"inputs": {**failure["inputs"], "location": saved_profile["location"]}, "profiles": [saved_profile], "revision": uuid4().hex}
                st.session_state.pop("_profile_lookup_failure", None)
                st.rerun()

    pending = st.session_state.get("_pending_analysis")
    if pending:
        st.subheader("Confirm the correct business")
        profiles = pending["profiles"]
        token = pending["revision"]
        choice = st.selectbox("Matching profile", list(range(len(profiles))),
                              format_func=lambda i: f"{profiles[i]['name']} · {profiles[i]['location']}", key=f"confirm_profile_{token}")
        profile = profiles[choice]
        st.write("**Business:**", profile["name"])
        st.write("**Address:**", profile["location"])
        st.caption(f"Source: {profile['source']} · Coordinates: {profile['latitude']}, {profile['longitude']}")
        confirmed_website = st.text_input("Website for this profile (optional)", value=profile.get("website", ""), key=f"confirm_website_{token}_{choice}")
        st.caption("Google Business Profile and Meta Page resolution are not included in this lookup. Check that any website belongs to this business.")
        accepted = True
        if profile.get("resolution_status") == "area_center":
            st.warning("The exact store was not found. This profile uses an approximate area centre; distances will not be from the actual store.")
            accepted = st.checkbox("Use this approximate area for the search", key=f"confirm_area_{token}")
        confirm = st.button("Confirm profile and analyse", type="primary", disabled=not accepted, key="auto_confirm_profile")
        if st.button("Cancel profile selection", key="auto_cancel_profile"):
            st.session_state.pop("_pending_analysis", None)
            st.rerun()
        if confirm:
            inputs = {**pending["inputs"], "website": confirmed_website.strip()}
            selected_profile = {**profile, "website": confirmed_website.strip(), "User confirmed": True}
            st.session_state["automatic_inputs"] = inputs
            _run_confirmed_analysis(inputs, selected_profile)

    if st.session_state.get("_analysis_review_step") == "details":
        st.button("Continue to confirmed profile", on_click=review_analysis_step,
                  args=("profile",), key="details_forward_profile")
        return
    if st.session_state.get("competitor_selection_mode") == "pending_review":
        _render_competitor_review()
    else:
        _render_latest_analysis()


def _run_confirmed_analysis(inputs, profile):
    with st.status("Starting analysis...", expanded=True) as status:
        indicator = st.progress(0)
        def update(message, fraction):
            status.update(label=message)
            st.write(message)
            indicator.progress(fraction)
        try:
            run_automatic_analysis(st.session_state, **inputs, progress=update, confirmed_profile=profile, prepare_report=False)
            status.update(label="Candidates ready — review and approve competitors", state="complete", expanded=False)
            st.session_state.pop("_pending_analysis", None)
            st.session_state.pop("_analysis_review_step", None)
            st.rerun()
        except Exception as error:
            status.update(label="Search could not finish", state="error", expanded=True)
            st.error(str(error))
            st.info("Any previous successful analysis is still available below. Check the business name and location before trying again.")


def _render_competitor_review():
    from services.candidate_rules import remove_saved_self_listings
    if remove_saved_self_listings(st.session_state):
        st.info("Removed a duplicate listing of your own business from the competitor selection. Review the remaining candidates before creating a report.")
    from dashboard.competitor_management import render_competitor_management
    from services.competitor_evidence import competitor_id
    business = st.session_state.get("business_profile", {})
    st.subheader("Review competitors before creating the report")
    st.write(f"Confirmed business: {business.get('name', 'Your business')}")
    for warning in st.session_state.get("automatic_warnings", []):
        st.warning(warning)
    if not st.session_state.get("discovered_competitors") and not st.session_state.get("approved_competitors"):
        st.caption("Your confirmed location is kept. Retry when the map service recovers, or add known competitors below. An empty map response does not establish that no competitors exist.")
        if st.button("Retry competitor discovery", key="auto_retry_discovery"):
            from dashboard.competitor_discovery import fetch_nearby_businesses
            search = st.session_state.get("competitor_search_key")
            if search and len(search) == 5:
                fetch_nearby_businesses.clear(business["latitude"], business["longitude"], search[3], search[4] * 1000)
                inputs = dict(name=business["name"], location=business["location"], category=search[3], radius=search[4],
                              website=business.get("website", ""), include_websites=st.session_state.get("automatic_inputs", {}).get("include_websites", True))
                _run_confirmed_analysis(inputs, business)
    render_competitor_management()
    approved = st.session_state.get("approved_competitors", [])
    candidates = st.session_state.get("classified_competitors") or st.session_state.get("discovered_competitors", [])[:15]
    rows = list({competitor_id(row): row for row in candidates + approved}.values())
    approved_ids = {competitor_id(row) for row in approved}
    if any(row.get("Outside search radius") for row in rows):
        st.warning("A user-added candidate is outside the selected search radius. Check its distance before including it.")
    if not rows:
        st.info("Add a competitor above, or start a new business search.")
        return
    st.caption("AI labels are estimates. Uncheck unrelated businesses. New user-added businesses remain unclassified until reviewed. Search prominence is unavailable.")
    version = hashlib.sha256(json.dumps([st.session_state.get("competitor_search_key"), rows, sorted(approved_ids)], sort_keys=True, default=str).encode()).hexdigest()[:16]
    frame = pd.DataFrame([{"Include": competitor_id(row) in approved_ids, "Name": row["Name"], "Distance (km)": row.get("Distance (km)"),
                           "Classification": row.get("Classification", "Not classified"), "Relevance score": row.get("Relevance score"),
                           "Target ID": competitor_id(row)} for row in rows])
    edited = st.data_editor(frame, hide_index=True, disabled=[key for key in frame.columns if key != "Include"],
                            column_config={"Target ID": None}, key=f"auto_review_{version}", width="stretch")
    if st.button("Approve competitors and create report", type="primary", key="auto_approve_report"):
        selected_ids = set(edited.loc[edited["Include"], "Target ID"])
        if not selected_ids:
            st.warning("Select at least one competitor to create a report.")
            return
        previous = st.session_state["approved_competitors"]
        st.session_state["approved_competitors"] = [{**row, "Selection": "User approved"} for row in rows if competitor_id(row) in selected_ids]
        st.session_state["competitor_selection_mode"] = "manual"
        try:
            with st.spinner("Creating your report from the approved selection..."):
                generate_saved_report(st.session_state)
            st.session_state["main_navigation"] = "Overview"
            st.session_state.pop("_analysis_review_step", None)
            st.rerun()
        except (ValueError, OSError) as error:
            st.session_state["approved_competitors"] = previous
            st.session_state["competitor_selection_mode"] = "pending_review"
            st.error(str(error))


def _render_latest_analysis():
    if st.session_state.get("business_confirmed") and st.session_state.get("approved_competitors"):
        business = st.session_state.get("business_profile", {})
        if business.get("latitude") is None or business.get("longitude") is None:
            return  # Old manual profiles have no current analysis; do not add a second unrelated error.
        search = st.session_state.get("competitor_search_key")
        identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
        if not search or tuple(search[:3]) != identity:
            st.info("Run an analysis for your current business to see its results here.")
            return
        enriched_business, enriched_competitors = enrich_report_inputs(
            business, st.session_state["approved_competitors"], st.session_state.get("competitor_evidence", {}), st.session_state.get("scoring_weights", {})
        )
        signature = report_signature(enriched_business, enriched_competitors)
        if st.session_state.get("ai_insights_input") != signature:
            st.session_state.pop("ai_insights_report", None)
        st.divider()
        st.subheader(f"Latest result: {business.get('name', 'Your business')}")
        approved = st.session_state["approved_competitors"]
        unclassified = sum(row.get("Classification") not in {"Direct", "Indirect", "Irrelevant"} for row in approved)
        st.write(f"{len(approved)} nearby businesses selected · {search[4]} km search radius")
        notices = []
        if business.get("resolution_status") == "area_center":
            notices.append("Store location is unverified; distances use the area centre.")
        if unclassified:
            notices.append(f"{unclassified} businesses are not classified yet.")
        if any("limited best matches" in row.get("Discovery source", "") for row in approved):
            notices.append("Search coverage is limited.")
        if notices:
            st.warning(" ".join(notices) + " See search notes below.")
        with st.expander("Search notes and matched address"):
            st.write(business.get("location", "Address unavailable"))
            st.caption("Check this is the correct branch. AI classifications are estimates. Use Advanced tools to correct the business or competitor selection.")
            for warning in st.session_state.get("automatic_warnings", []):
                st.write(warning)
        st.button("Open dashboard", key="auto_view_results", on_click=navigate_to, args=("Overview",))
        has_report = bool(st.session_state.get("ai_insights_report"))
        factual = False
        if not has_report:
            st.info("Your businesses are saved. Create a report from this data, even when AI is unavailable.")
            factual = st.button("Create report from saved data", key="auto_factual_report", type="primary")
        with st.expander("Update report or evidence"):
            st.caption("Optional. Regenerating a report does not repeat the business search. Gemini free-tier limits still apply.")
            retry_label = "Retry AI report" if st.session_state.get("report_generation_note") else "Regenerate report"
            retry_ai = st.button(retry_label, key="auto_retry_report")
            if has_report:
                factual = st.button("Generate factual report (no AI)", key="auto_factual_report")
            render_website_checks()
            review_business, review_competitors = enrich_report_inputs(st.session_state["business_profile"], st.session_state["approved_competitors"], st.session_state.get("competitor_evidence", {}), st.session_state.get("scoring_weights", {}))
            render_evidence_review(review_business, review_competitors)
        if retry_ai or factual:
            with st.status("Generating report...", expanded=True) as status:
                try:
                    generate_saved_report(st.session_state, use_ai=not factual)
                    # Keep classification warnings, but clear a recovered report failure.
                    st.session_state["automatic_warnings"] = [w for w in st.session_state.get("automatic_warnings", []) if not w.startswith("Your discovered businesses are saved")]
                    status.update(label="Factual report ready" if st.session_state.get("report_generation_note") else "Report ready", state="complete", expanded=False)
                except Exception as error:
                    status.update(label="Report unavailable — your businesses are saved", state="error")
                    st.error(str(error))
        report = st.session_state.get("ai_insights_report")
        if warning := st.session_state.get("analysis_history_warning"):
            st.warning(warning)
        if report:
            if note := st.session_state.get("report_generation_note"):
                st.caption("Factual report available. AI suggestions were not used; see the report for its limitations.")
            pdf_bytes = create_pdf_report(report)
            st.download_button("Download PDF report", pdf_bytes, "CompeteRivio_AI_Report.pdf", "application/pdf", key="auto_pdf_report", type="primary")
            with st.expander("Preview report"):
                st.markdown(report)
            with st.expander("More download formats"):
                st.download_button("Download report text", report, "CompeteRivio_AI_Report.md", "text/markdown", key="auto_text_report")
                render_bundle_download(current_snapshot(st.session_state), pdf_bytes, "auto_analysis_bundle")
