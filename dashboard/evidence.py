import io
import json
import hashlib
import pandas as pd
import streamlit as st
from dashboard.scoring_weights import render_scoring_weights
from dashboard.evidence_review import render_evidence_review
from dashboard.google_ratings import render_google_ratings

from services.competitor_evidence import (
    METRICS, CATEGORIES, evidence_scope, build_targets, validate_evidence, calculate_scores, enrich_report_inputs,
)


def render_evidence():
    st.subheader("Competitor evidence and scores")
    st.caption("Enter information you collected yourself. No paid APIs are called on this page.")
    business = st.session_state.get("business_profile", {})
    approved = st.session_state.get("approved_competitors", [])
    search = st.session_state.get("competitor_search_key")
    business_key = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not st.session_state.get("business_confirmed") or not approved or not search or tuple(search[:3]) != business_key:
        st.info("Confirm a business and approve its competitors first.")
        return
    scope = evidence_scope(business)
    render_google_ratings()
    targets = build_targets(business, approved)
    all_evidence = st.session_state.get("competitor_evidence", {})
    evidence = all_evidence.get(scope, {})
    frame = pd.DataFrame([
        {**target, **{metric: evidence.get(target["Target ID"], {}).get(metric) for metric in METRICS},
         "Source": evidence.get(target["Target ID"], {}).get("Source", ""),
         "Observed On": evidence.get(target["Target ID"], {}).get("Observed On", "")}
        for target in targets
    ])
    # Keep blank metrics numeric so an initially empty table accepts numbers.
    for metric in METRICS:
        frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    allowed = {target["Target ID"] for target in targets}
    st.info("Blank means Unavailable; enter 0 only when you have evidence of zero. Add a source and observation date (YYYY-MM-DD) for every row containing measurements.")
    st.caption("Source and date apply to all measurements in a row. Compare the same geography, time period, and keyword definitions. User-entered data is not independently verified.")
    st.download_button("Download CSV template / current evidence", frame.to_csv(index=False).encode("utf-8-sig"),
                       "CompeteRivio_Evidence.csv", "text/csv", key="download_evidence_template")
    uploaded = st.file_uploader("Import completed evidence CSV", type=["csv"], key="evidence_upload")
    if st.button("Import CSV", disabled=uploaded is None):
        try:
            imported = pd.read_csv(io.BytesIO(uploaded.getvalue()), dtype=str, keep_default_na=False, encoding="utf-8-sig")
            if "Target ID" not in imported.columns or imported.empty:
                raise ValueError("CSV must contain Target ID and at least one row.")
            unknown = set(imported.columns) - set(frame.columns)
            if unknown:
                raise ValueError(f"Unknown columns: {', '.join(sorted(unknown))}. Use the template headers.")
            changes = validate_evidence(imported.to_dict("records"), allowed)
            st.session_state["competitor_evidence"] = {**all_evidence, scope: {**evidence, **changes}}
            st.session_state["_evidence_notice"] = f"Imported {len(changes)} evidence rows."
            st.rerun()
        except (ValueError, UnicodeError, pd.errors.ParserError) as error:
            st.error(str(error))
    if notice := st.session_state.pop("_evidence_notice", None):
        st.success(notice)
    version = hashlib.sha256(json.dumps([scope, evidence], sort_keys=True).encode()).hexdigest()[:16]
    with st.form("competitor_evidence_form"):
        edited = st.data_editor(
            frame, hide_index=True, width="stretch", disabled=["Target ID", "Name"],
            key=f"evidence_editor_{version}",
            column_config={
                "Rating": st.column_config.NumberColumn(min_value=0, max_value=5, step=0.1),
                **{metric: st.column_config.NumberColumn(min_value=0, step=1) for metric in METRICS if metric != "Rating"},
                "Observed On": st.column_config.TextColumn(help="YYYY-MM-DD, e.g. 2026-10-25"),
            },
        )
        save = st.form_submit_button("Save evidence and calculate scores", type="primary")
    if save:
        try:
            cleaned = edited.astype(object).where(pd.notna(edited), None)
            changes = validate_evidence(cleaned.to_dict("records"), allowed)
            st.session_state["competitor_evidence"] = {**all_evidence, scope: {**evidence, **changes}}
            st.session_state["_evidence_notice"] = "Evidence saved. Scores recalculated."
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    weights = render_scoring_weights(business)
    enriched_business, enriched_competitors = enrich_report_inputs(business, approved, all_evidence, {scope: weights})
    render_evidence_review(enriched_business, enriched_competitors)
    render_scores(targets, evidence, weights)


def render_scores(targets, evidence, weights=None):
    scores = calculate_scores(targets, evidence, weights)
    st.subheader("Evidence score comparison")
    st.caption("This is a partial evidence score, not the full seven-category Competitive Strength Score.")
    with st.expander("How scores are calculated", expanded=True):
        st.write("Only categories with complete measurements for your business AND every approved competitor are used. The same categories and weights apply to everyone.")
        st.write("Each metric: 100 × (value − minimum) / (maximum − minimum). Equal values receive a neutral 50. Reputation averages normalized rating and review count.")
        st.write("Score = sum(category score × category weight) / sum(included weights). Missing values never become zero. Scores are relative to this selection, not absolute quality ratings.")
        st.write("Measured categories: Reputation, Paid activity, and Keyword strategy. Search visibility, social presence, website quality, and local presence remain unavailable. Website page terms do not supply those missing performance measurements.")
        st.write("Default evidence coverage uses the original seven-category weights (maximum 50% with the current data fields). Chosen-weight coverage measures supported weights under your configuration. Setting unavailable categories to zero can make chosen-weight coverage 100%, but does not complete the seven-category analysis.")
        st.caption("Ad count and keyword count are limited proxies; this does not implement the PRD's complete marketing metrics. Threat levels and keyword gaps are not inferred.")
    coverage = scores[0]["PRD weight coverage (%)"] if scores else 0
    chosen_coverage = scores[0]["Selected weight coverage (%)"] if scores else 0
    gap = scores[0].get("Gap vs competitor average") if scores else None
    columns = st.columns(3)
    columns[0].metric("Default evidence coverage", f"{coverage}%")
    columns[1].metric("Chosen-weight coverage", f"{chosen_coverage:g}%")
    columns[2].metric("Your partial score gap", f"{gap:+.2f} pts" if gap is not None else "Unavailable")
    st.caption("Score gap = your partial score minus the selected competitors' average. This compares the supplied evidence, not commercial performance.")
    if not coverage:
        st.info("Comparable scores require a positive weight and complete evidence for at least one supported category across your business and every approved competitor.")
    display = []
    for row in scores:
        display.append({"Name": row["Name"], "Evidence score": row["Evidence score"],
                        **{category: row["Breakdown"].get(category) for category in CATEGORIES}})
    table = pd.DataFrame(display).sort_values("Evidence score", ascending=False, na_position="last")
    st.dataframe(table.fillna("Unavailable"), hide_index=True, width="stretch")
    with st.expander("Score breakdown by category"):
        breakdown = [{"Name": row["Name"], "Category": category, "Category score": value,
                      "Included weight (%)": row["Included weight shares (%)"][category],
                      "Contribution to score": row["Category contributions"][category]}
                     for row in scores for category, value in row["Breakdown"].items()]
        if breakdown:
            st.dataframe(pd.DataFrame(breakdown), hide_index=True, width="stretch")
            st.caption("Small differences in totals can occur from rounding.")
        else:
            st.info("No comparable categories with positive weights yet.")
    export = pd.DataFrame([{**target, **evidence.get(target["Target ID"], {}),
                            "Evidence score": score["Evidence score"], "PRD weight coverage (%)": coverage,
                            "Chosen-weight coverage (%)": chosen_coverage,
                            "Applied weights": json.dumps(score["Applied weights"]),
                            "Category contributions": json.dumps(score["Category contributions"]),
                            "Gap vs competitor average": score.get("Gap vs competitor average")}
                           for target, score in zip(targets, scores)])
    st.download_button("Download evidence and scores (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                       "CompeteRivio_Evidence_Scores.csv", "text/csv", key="download_evidence_scores")
