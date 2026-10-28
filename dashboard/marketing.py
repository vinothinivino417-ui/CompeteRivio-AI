import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.theme import THEMES
from services.marketing_analysis import build_marketing_evidence


def render_marketing():
    st.subheader("Marketing evidence comparison")
    st.caption("Saved ad-count observations and captured website messaging. This page does not call a paid API or retrieve Meta advertisements.")
    business = st.session_state.get("business_profile", {})
    competitors = st.session_state.get("approved_competitors", [])
    search = st.session_state.get("competitor_search_key")
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not st.session_state.get("business_confirmed") or not competitors or not search or tuple(search[:3]) != identity:
        st.info("Run Automatic Analysis or approve competitors for the current business first.")
        return
    rows = build_marketing_evidence(business, competitors, st.session_state.get("competitor_evidence", {}))
    observed = [row for row in rows if row["Active Ads"] is not None]
    websites = [row for row in rows if row["Website evidence usable"]]
    columns = st.columns(3)
    columns[0].metric("Businesses with ad-count evidence", f"{len(observed)} / {len(rows)}")
    columns[1].metric("Businesses with website evidence", f"{len(websites)} / {len(rows)}")
    columns[2].metric("Ad observation dates", len({row["Ad-count observed on"] for row in observed}))
    focus = st.selectbox("Show businesses", ["All businesses", "Ad-count evidence available", "Website evidence available"], key="marketing_focus", persist_state="session")
    filtered = observed if focus == "Ad-count evidence available" else websites if focus == "Website evidence available" else rows
    st.subheader("User-provided advertising activity")
    st.caption("Blank means unavailable. A sourced observation of zero remains zero. Counts are not automatically verified and may describe different platforms, scopes, or dates.")
    ad_table = pd.DataFrame([{key: row[key] for key in ("Business", "Active Ads", "Ad-count source", "Ad-count observed on", "Ad-count status")} for row in filtered])
    if not ad_table.empty:
        display = ad_table.copy()
        display["Active Ads"] = [str(int(value)) if pd.notna(value) else "Unavailable" for value in display["Active Ads"]]
        for field in ("Ad-count source", "Ad-count observed on"):
            display[field] = display[field].replace("", "Unavailable")
        st.dataframe(display, hide_index=True, width="stretch")
    else:
        st.info("No businesses match this evidence filter.")
    if not observed:
        st.info("No ad-count observations yet. In Evidence & Scores, enter Active Ads with its source and observation date, or import the completed CSV template.")
    else:
        dates = {row["Ad-count observed on"] for row in observed}
        if len(dates) > 1:
            st.warning("Ad observations have different dates. Compare only like-for-like sources and time periods; these are not live ad counts.")
        chart_rows = [row for row in filtered if row["Active Ads"] is not None]
        if chart_rows:
            colors = THEMES.get(st.session_state.get("appearance_mode"), THEMES["Dark"])
            chart = go.Figure(go.Bar(
                x=[row["Label"] for row in chart_rows], y=[row["Active Ads"] for row in chart_rows],
                marker_color=colors["accent"], text=[row["Active Ads"] for row in chart_rows], textposition="outside", cliponaxis=False,
                customdata=[[row["Ad-count source"], row["Ad-count observed on"]] for row in chart_rows],
                hovertemplate="%{x}<br>Observed active ads: %{y}<br>Source: %{customdata[0]}<br>Observed: %{customdata[1]}<extra></extra>",
            ))
            chart.update_layout(template="streamlit", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                height=400, showlegend=False,
                                yaxis=dict(title="Observed active-ad count", range=[0, max(1, max(row["Active Ads"] for row in chart_rows) * 1.2)],
                                           dtick=1 if max(row["Active Ads"] for row in chart_rows) <= 10 else None, tickformat=",.0f"),
                                xaxis=dict(automargin=True))
            st.plotly_chart(chart, width="stretch", theme="streamlit", key="observed_ad_counts")

    st.subheader("Messaging observed on public webpages")
    st.caption("These are captured titles, descriptions, and link labels, not Meta ad creatives. Website ownership and branch identity are not independently verified.")
    visible_websites = [row for row in filtered if row["Website evidence usable"]]
    if not visible_websites:
        st.info("No usable website evidence yet. In Automatic Analysis, open Website evidence and click Check websites after supplying any missing URL." if not websites else "No website messaging matches the current business filter.")
    for row in visible_websites:
        with st.container(border=True):
            st.write(f"**{row['Label']}**")
            st.write("Webpage title:", row["Webpage title"] or "Not found in captured HTML")
            st.write("Description:", row["Webpage description"] or "Not found in captured HTML")
            st.write("Headings:", row["Website headings"] or "Not found in captured HTML")
            st.write("Service/product link labels:", row["Service/product link labels"] or "Not found in captured HTML")
            st.write("Source URL:", row["Website source URL"])
            st.caption(f"Retrieved at (UTC): {row['Website retrieved at (UTC)']}")
    with st.expander("Marketing data availability", expanded=True):
        st.write("Meta creative images, ad formats, run duration, followers, engagement, and historical ad trends: Unavailable. The app saves the latest workspace, not a historical marketing time series.")
        st.write("No share-of-voice, ad-performance, or customer-segment conclusions are inferred from website copy or missing measurements.")
        st.dataframe(pd.DataFrame([{key: row[key] for key in ("Business", "Website status", "Website source URL", "Website retrieved at (UTC)", "Website note")} for row in rows]), hide_index=True, width="stretch")
    st.download_button("Download all marketing evidence (CSV)", pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
                       "CompeteRivio_Marketing_Evidence.csv", "text/csv", key="download_marketing_evidence")
