import pandas as pd
import plotly.express as px
import streamlit as st

from services.lighthouse_audit import parse_lighthouse_report


def render_lighthouse_audits():
    with st.expander("Website audit · automatic checks and Lighthouse reports"):
        st.write("Compare measured website performance, accessibility, best practices and SEO scores.")
        entities = [st.session_state.get("business_profile", {})] + st.session_state.get("approved_competitors", [])
        automatic = [{"Business": item.get("name", item.get("Name", "Business")), **item["Lighthouse audit"]}
                     for item in entities if item.get("Lighthouse audit")]
        if automatic:
            st.caption("Automatic results for the current selection. Google PageSpeed may reject keyless requests or take too long; missing measurements stay unavailable.")
            st.dataframe(pd.DataFrame(automatic), hide_index=True, width="stretch")
            measured = [row for row in automatic if row.get("Status") == "Available"]
            if measured:
                comparison = pd.DataFrame(measured).melt(id_vars=["Business"], value_vars=["Performance", "Accessibility", "Best practices", "SEO"], var_name="Category", value_name="Score").dropna(subset=["Score"])
                figure = px.bar(comparison, x="Category", y="Score", color="Business", barmode="group",
                                color_discrete_sequence=["#2563EB", "#DC2626", "#10B981"])
                figure.update_layout(template="streamlit", yaxis_range=[0, 100], height=360)
                st.plotly_chart(figure, theme="streamlit", width="stretch", key="automatic_audit_chart")
            st.download_button("Download automatic website audits (CSV)", pd.DataFrame(automatic).to_csv(index=False).encode("utf-8-sig"), "CompeteRivio_Automatic_Audits.csv", "text/csv")
        st.caption("In Chrome: open a website → F12 → Lighthouse → Analyze page load → export JSON. Upload that JSON below. No API key or paid service is needed. Uploads are user-supplied evidence; website ownership is not verified.")
        with st.form("lighthouse_upload_form"):
            upload = st.file_uploader("Lighthouse JSON report (maximum 10 MB)", type=["json"], key="lighthouse_upload")
            save = st.form_submit_button("Save website audit")
        if save:
            if upload is None:
                st.warning("Choose a Lighthouse JSON report first.")
            else:
                try:
                    audit = parse_lighthouse_report(upload.getvalue())
                    audits = dict(st.session_state.get("website_audits", {}))
                    identity = audit["Website"] + "|" + str(audit["Device"])
                    if identity not in audits and len(audits) >= 50:
                        raise ValueError("The 50-audit limit has been reached. Remove a saved audit first.")
                    audits[identity] = audit
                    st.session_state["website_audits"] = audits
                    st.success("Website audit saved. Matching website/device entries replace the previous audit.")
                except (ValueError, TypeError, AttributeError) as error:
                    st.error(str(error))
        audits = st.session_state.get("website_audits", {})
        if not audits:
            return
        data = pd.DataFrame(audits.values())
        st.dataframe(data, hide_index=True, width="stretch")
        scores = data.melt(id_vars=["Website", "Device"],
                           value_vars=["Performance", "Accessibility", "Best practices", "SEO"],
                           var_name="Category", value_name="Score").dropna(subset=["Score"])
        scores["Website / device"] = scores["Website"] + " · " + scores["Device"].astype(str)
        chart = px.bar(scores, x="Category", y="Score", color="Website / device", barmode="group",
                       color_discrete_sequence=["#2563EB", "#DC2626", "#10B981", "#64748B"])
        chart.update_layout(template="streamlit", yaxis_range=[0, 100], height=360)
        st.plotly_chart(chart, theme="streamlit", width="stretch")
        st.caption("Scores are out of 100. Blank means unavailable. Compare the same device and similar test conditions. These audits are separate from competitor strength scores and PDF reports.")
        st.download_button("Download website audits (CSV)", data.to_csv(index=False).encode("utf-8-sig"),
                           "CompeteRivio_Website_Audits.csv", "text/csv", key="lighthouse_csv")
        selected = st.selectbox("Saved audit to remove", list(audits), key="lighthouse_remove_selection")
        if st.button("Remove selected audit", key="lighthouse_remove"):
            st.session_state["website_audits"] = {key: value for key, value in audits.items() if key != selected}
            st.rerun()
