import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.theme import THEMES
from services.keyword_analysis import build_keyword_analysis
from services.keyword_intent import INTENT_GROUPS


def render_keywords():
    st.subheader("Website keyword comparison")
    st.caption("Observed webpage terms and declared meta keywords from saved website checks. No paid keyword API is used.")
    business = st.session_state.get("business_profile", {})
    competitors = st.session_state.get("approved_competitors", [])
    search = st.session_state.get("competitor_search_key")
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not st.session_state.get("business_confirmed") or not competitors or not search or tuple(search[:3]) != identity:
        st.info("Run Automatic Analysis or approve competitors for the current business first.")
        return
    analysis = build_keyword_analysis(business, competitors)
    entities = analysis["Entities"]
    st.info("Search volumes and Google positions are unavailable. Intent groups are rule-based estimates, not measured search behaviour. 'Not captured' means absent from the extracted sample, not absent from the whole website or search strategy.")
    if not analysis["Terms"]:
        st.info("No usable website terms yet. In Automatic Analysis, open Website evidence, supply a website URL if missing, and click Check websites. Blocked or script-only pages may remain unavailable.")
        _show_sources(entities)
        return
    usable = [entity for entity in entities if entity["Usable"]]
    columns = st.columns(3)
    columns[0].metric("Captured candidate terms", len(analysis["Terms"]))
    columns[1].metric("Businesses with usable terms", f"{len(usable)} / {len(entities)}")
    columns[2].metric("Distinct source URLs", len({entity["Source URL"] for entity in usable if entity["Source URL"]}))
    if not entities[0]["Usable"]:
        st.warning("Your business page has no usable captured terms. Competitor terms are shown, but content gaps cannot be determined.")
    if len({entity["Source URL"] for entity in usable}) < len(usable):
        st.caption("Some businesses share a website source. These observations may describe a chain website, not an individual branch.")

    st.write("**Estimated intent groups by business**")
    intent_chart = go.Figure()
    palette = {"Branded": "#2563EB", "Service": "#10B981", "Location": "#DC2626", "Informational": "#D97706", "Unclassified": "#94A3B8"}
    for group in INTENT_GROUPS:
        intent_chart.add_bar(name=group, x=[entity["Label"] for entity in usable],
                             y=[len(entity["Intent groups"][group]) for entity in usable], marker_color=palette[group])
    intent_chart.update_layout(template="streamlit", barmode="stack", height=340, yaxis_title="Captured terms (not search volume)", legend_title_text="Estimated intent")
    st.plotly_chart(intent_chart, width="stretch", theme="streamlit", key="keyword_intent_groups")
    st.caption("Rules use business names, supplied locations and a small cue-word vocabulary. Priority: Informational → Branded → Location → Service; ambiguous terms stay Unclassified. Labels need review and may be less useful for unsupported languages. Businesses without usable page terms are excluded, rather than scored zero.")
    focus = st.selectbox("Show terms", ["All captured terms", "Potential content gap", "Shared captured term", "Captured on your page"], key="keyword_focus", persist_state="session")
    intent = st.selectbox("Estimated intent", ["All groups", *INTENT_GROUPS], key="keyword_intent_filter")
    query = st.text_input("Find a captured term", key="keyword_query", persist_state="session")
    table = pd.DataFrame(analysis["Rows"])
    filtered = table if focus == "All captured terms" else table[table["Review"] == focus]
    if intent != "All groups":
        filtered = filtered[filtered["Intent group (estimate)"] == intent]
    if query.strip():
        filtered = filtered[filtered["Term"].str.contains(query.strip(), case=False, regex=False)]
    st.dataframe(filtered, hide_index=True, width="stretch")
    st.caption("Potential gaps are terms captured for competitors but not in your captured sample. Review their relevance before changing content.")
    if not filtered.empty:
        colors = THEMES.get(st.session_state.get("appearance_mode"), THEMES["Dark"])
        selected_terms = filtered["Term"].tolist()[:30]
        values, hover = [], []
        for term in selected_terms:
            values.append([1 if term in entity["Terms"] else 0 if entity["Usable"] else -1 for entity in entities])
            hover.append([f"{entity['Label']}<br>{term}<br>{'Captured' if term in entity['Terms'] else 'Not captured in sample' if entity['Usable'] else 'Unavailable'}" for entity in entities])
        unknown = "#94A3B8" if st.session_state.get("appearance_mode") == "Light" else "#475569"
        not_captured = "#E8F0EB" if st.session_state.get("appearance_mode") == "Light" else "#24354A"
        heatmap = go.Figure(go.Heatmap(
            z=values, x=[entity["Label"] for entity in entities], y=selected_terms,
            zmin=-1, zmax=1,
            colorscale=[[0, unknown], [.249, unknown], [.25, not_captured], [.749, not_captured], [.75, colors["accent"]], [1, colors["accent"]]],
            customdata=hover, hovertemplate="%{customdata}<extra></extra>",
            colorbar=dict(tickvals=[-1, 0, 1], ticktext=["Unavailable", "Not captured", "Captured"]),
        ))
        _style_chart(heatmap, colors)
        heatmap.update_layout(height=max(380, len(selected_terms) * 25 + 160), margin=dict(l=20, r=50, t=30, b=100))
        heatmap.update_yaxes(autorange="reversed", automargin=True)
        st.write("**Captured-term overlap**")
        st.plotly_chart(heatmap, width="stretch", theme="streamlit", key="captured_term_heatmap")
        st.caption("Showing up to 30 filtered terms. Colours describe captured observations, not rankings.")

        counts = go.Figure(go.Bar(
            x=[len(entity["Terms"]) for entity in usable], y=[entity["Label"] for entity in usable],
            orientation="h", marker_color=colors["accent"], hovertemplate="%{y}<br>%{x} captured terms<extra></extra>",
        ))
        _style_chart(counts, colors)
        counts.update_layout(height=max(300, len(usable) * 35 + 100), xaxis_title="Unique terms captured in this sample")
        st.write("**Captured terms by business**")
        st.plotly_chart(counts, width="stretch", theme="streamlit", key="captured_terms_by_business")
    st.download_button("Download term comparison (CSV)", table.to_csv(index=False).encode("utf-8-sig"), "CompeteRivio_Captured_Terms.csv", "text/csv", key="download_captured_terms")
    st.download_button("Download term sources (CSV)", pd.DataFrame(analysis["Observations"]).to_csv(index=False).encode("utf-8-sig"), "CompeteRivio_Term_Sources.csv", "text/csv", key="download_term_sources")
    _show_sources(entities)


def _show_sources(entities):
    with st.expander("Source pages and data availability", expanded=True):
        st.dataframe(pd.DataFrame([
            {key: entity[key] for key in ("Evidence ID", "Name", "Website status", "Source URL", "Retrieved at (UTC)", "Note")}
            for entity in entities
        ]), hide_index=True, width="stretch")


def _style_chart(chart, colors):
    chart.update_layout(template="streamlit", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(automargin=True), yaxis=dict(automargin=True), showlegend=False)
