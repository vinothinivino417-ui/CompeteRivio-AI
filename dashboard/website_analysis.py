import pandas as pd
import streamlit as st

from services.automatic_analysis import check_saved_websites
from dashboard.lighthouse_audit import render_lighthouse_audits


def render_website_checks():
    render_lighthouse_audits()
    business = st.session_state.get("business_profile", {})
    competitors = st.session_state.get("approved_competitors", [])
    with st.expander("Website evidence - free public-page checks"):
        st.caption("Checks listed/supplied URLs only. Up to eight HTML checks and two mobile quality audits per run; successful results are cached for a day. Public-page checks respect robots.txt. Accessible URLs are sent to Google PageSpeed for Lighthouse auditing; quotas may limit results. Missing or blocked websites remain unavailable.")
        with st.form("saved_website_check_form"):
            website = st.text_input("Website for the saved business (optional)", value=business.get("website") or "")
            check = st.form_submit_button("Check websites")
        if check:
            # This is an explicit correction to the current business's supplied URL.
            st.session_state["business_profile"] = {**business, "website": (website or "").strip()}
            with st.status("Checking public websites...", expanded=True) as status:
                try:
                    check_saved_websites(st.session_state, st.write)
                    status.update(label="Website checks finished", state="complete", expanded=False)
                    st.session_state["_website_notice"] = "Website checks saved. Generate the report below to include them."
                    st.rerun()
                except (ValueError, OSError) as error:
                    status.update(label="Website checks could not finish", state="error")
                    st.error(str(error))
        if notice := st.session_state.pop("_website_notice", None):
            st.success(notice)
        entities = [(business.get("name", "Your business"), business)] + [(row.get("Name", "Business"), row) for row in competitors]
        table = []
        for name, entity in entities:
            audit = entity.get("Website analysis", {})
            table.append({"Business": name, "Status": audit.get("Status", "Not checked"),
                          "Page title": audit.get("Page title", "Unavailable"),
                          "Source URL": audit.get("Source URL", entity.get("website", entity.get("Website", ""))),
                          "Retrieved at (UTC)": audit.get("Retrieved at (UTC)", ""), "Note": audit.get("Reason", audit.get("Scope", ""))})
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
        export = [{"Business": name, **{key: "; ".join(value) if isinstance(value, list) else value
                                       for key, value in entity.get("Website analysis", {}).items()}}
                  for name, entity in entities]
        st.download_button("Download website evidence (CSV)", pd.DataFrame(export).to_csv(index=False).encode("utf-8-sig"),
                           "CompeteRivio_Website_Evidence.csv", "text/csv", key="download_website_evidence")
        for name, entity in entities:
            audit = entity.get("Website analysis", {})
            if audit.get("Status") != "Available":
                continue
            st.write(f"**{name}**")
            st.write("Description from webpage:", audit.get("Description") or "Not found in fetched HTML")
            st.write("Headings:", "; ".join(audit.get("Headings", [])) or "Not found in fetched HTML")
            st.write("Service/product link labels:", "; ".join(audit.get("Service/product link labels", [])) or "Not found in fetched HTML")
            st.write("On-page keyword candidates:", ", ".join(audit.get("On-page keyword candidates", [])) or "Not found in fetched HTML")
            st.write("Email links/text:", ", ".join(audit.get("Email links/text", [])) or "Not found in fetched HTML")
            st.write("Phone links:", ", ".join(audit.get("Phone links", [])) or "Not found in fetched HTML")
        st.caption("Page text is self-published evidence. Website ownership and branch identity are not verified. On-page words are not search volumes, rankings, or verified service offerings.")
