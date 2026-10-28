import pandas as pd
import streamlit as st

from services.evidence_review import build_evidence_review


def render_evidence_review(business, competitors):
    review = build_evidence_review(business, competitors)
    rows = review["Rows"]
    due = sum(row["Review status"] == "Review due" for row in rows)
    date_issues = sum(row["Review status"] in {"Date missing", "Date invalid", "Future date — check"} for row in rows)
    if due or date_issues:
        st.warning(f"Evidence review: {due} record(s) are at least 90 days old; {date_issues} have missing or questionable dates. Review these before relying on the report.")
    with st.expander("Evidence dates and review reminders"):
        st.caption(f"Checked as of {review['As of']} (India time). The 90-day window is a review reminder, not a verified expiry date or an accuracy rating. Recent data may still be incorrect. Reminders do not change your measurements or scores.")
        frame = pd.DataFrame(rows)
        frame["Age (days)"] = frame["Age (days)"].map(lambda value: "Unavailable" if pd.isna(value) else str(int(value)))
        st.dataframe(frame, hide_index=True, width="stretch")
        st.caption("Update manual measurements, sources, and dates in Evidence & Scores. To update captured pages, use the website checks in Automatic Analysis. Generating a report alone does not refresh evidence. Website age measures time since capture, not time since the website owner updated the page.")
        export = frame.assign(**{"Checked as of (India date)": review["As of"], "Review window (days)": review["Review after days"]})
        st.download_button("Download evidence review checklist (CSV)", export.to_csv(index=False).encode("utf-8-sig"), "CompeteRivio_Evidence_Review.csv", "text/csv", key="evidence_review_csv")
