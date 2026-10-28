import json
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.navigation import navigate_to, review_analysis_step
from dashboard.theme import CHART_COLORS
from services.dashboard_summary import summarize_selection, valid_distance
from services.analysis_history import current_snapshot
from services.report_export import create_pdf_report


def style_overview_chart(chart, colors=None):
    chart.update_layout(template="streamlit", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        height=310, margin=dict(l=15, r=25, t=25, b=20),
                        font=dict(size=13), legend=dict(orientation="h", y=-.12, title=None))


def render_overview_charts(approved):
    data = pd.DataFrame(approved)
    data["Classification"] = data.get("Classification", pd.Series("Not classified", index=data.index)).fillna("Not classified")
    data["Classification"] = data["Classification"].where(data["Classification"].isin(CHART_COLORS), "Not classified")
    counts = data["Classification"].value_counts().rename_axis("Classification").reset_index(name="Businesses")
    left, right = st.columns(2, gap="medium")
    with left, st.container(border=True):
        st.subheader("Competitor mix")
        st.caption("How your selected businesses are classified")
        chart = px.pie(counts, names="Classification", values="Businesses", color="Classification", hole=.72,
                       color_discrete_map=CHART_COLORS)
        chart.update_traces(textinfo="value", textposition="inside", hovertemplate="%{label}: %{value}<extra></extra>")
        style_overview_chart(chart)
        chart.add_annotation(text=str(len(approved)), x=.5, y=.5, showarrow=False, font=dict(size=32))
        st.plotly_chart(chart, width="stretch", theme="streamlit", key="overview_classifications")
    with right, st.container(border=True):
        st.subheader("Distance distribution")
        st.caption("Counts grouped by straight-line distance")
        summary = summarize_selection(approved)
        bands = pd.DataFrame({"Distance": ["Within 1 km", "1–2 km", "Beyond 2 km"], "Businesses": summary["distance_bands"]})
        chart = px.bar(bands, x="Distance", y="Businesses", color="Distance", text="Businesses",
                       color_discrete_map={"Within 1 km": "#10B981", "1–2 km": "#2563EB", "Beyond 2 km": "#EF4444"})
        chart.update_traces(textposition="outside", cliponaxis=False)
        style_overview_chart(chart)
        chart.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Businesses")
        chart.update_yaxes(dtick=1, rangemode="tozero", range=[0, max(1, max(summary["distance_bands"]) * 1.25)])
        st.plotly_chart(chart, width="stretch", theme="streamlit", key="overview_distance_bands")


def _nearest_chart(rows):
    distances = [{"Business": row.get("Name", "Unnamed"), "Distance (km)": distance,
                  "Classification": row.get("Classification", "Not classified")}
                 for row in rows if (distance := valid_distance(row.get("Distance (km)"))) is not None]
    st.subheader("Closest businesses")
    st.caption("The nearest six in your selection; proximity is not competitive strength.")
    if not distances:
        st.info("Distance data is unavailable for this selection.")
        return
    data = pd.DataFrame(distances).sort_values("Distance (km)").head(6)
    # Keep duplicate names separate without exposing long identifiers as chart labels.
    data["Business"] = [f"{index + 1}. {name}" for index, name in enumerate(data["Business"])]
    chart = px.bar(data, x="Distance (km)", y="Business", color="Classification", orientation="h",
                   color_discrete_map=CHART_COLORS, text="Distance (km)", category_orders={"Business": data["Business"].tolist()})
    chart.update_traces(texttemplate="%{x:.2f} km", textposition="outside", cliponaxis=False)
    style_overview_chart(chart)
    chart.update_layout(showlegend=False, height=340, xaxis_title="Distance (km)", yaxis_title=None, margin=dict(l=5,r=65,t=10,b=20))
    chart.update_yaxes(autorange="reversed", automargin=True)
    chart.update_xaxes(range=[0, max(.1, float(data["Distance (km)"].max()) * 1.28)])
    st.plotly_chart(chart, width="stretch", theme="streamlit", key="overview_nearest")


def _report_panel():
    st.subheader("Your report")
    snapshot = current_snapshot(st.session_state)
    if snapshot:
        st.success("Report ready to download")
        st.caption("Includes the current selection, available evidence, and labelled recommendations.")
        st.download_button("Download PDF report", create_pdf_report(snapshot["report"]), "CompeteRivio_AI_Report.pdf", "application/pdf",
                           type="primary", width="stretch", key="dashboard_pdf")
        st.button("Open saved reports", on_click=navigate_to, args=("Analysis History",), width="stretch", key="dashboard_history")
    else:
        st.info("Create or update the report for this selection.")
        st.button("Prepare report", on_click=navigate_to, args=("Automatic Analysis",), type="primary", width="stretch", key="dashboard_prepare_report")
    st.divider()
    st.write("**Improve this analysis**")
    st.caption("Check the selected businesses or add measurements with a source and date.")
    st.button("Review competitors", on_click=navigate_to, args=("Competitor Analysis",), width="stretch", key="dashboard_review")
    st.button("Add evidence", on_click=navigate_to, args=("Evidence & Scores",), width="stretch", key="dashboard_evidence")


def _empty_dashboard():
    with st.container(border=True, key="welcome_card"):
        st.caption("WELCOME TO COMPETERIVIO AI")
        st.header("Your local competitor picture, in one place.")
        st.write("Enter a business, explore nearby competitors, and download a clear report.")
        st.button("Start your first analysis", on_click=navigate_to, args=("Automatic Analysis",), type="primary", key="dashboard_get_started")
    columns = st.columns(3)
    for column, title, description in zip(columns, ["01 · Find", "02 · Compare", "03 · Download"],
            ["Search by business, location, and industry.", "Review the selection, charts, and map.", "Keep a PDF report and return to saved analyses."]):
        with column, st.container(border=True):
            st.subheader(title)
            st.caption(description)
    st.caption("Live discovery requires internet access. AI estimates and missing evidence are clearly labelled.")


def render_overview():
    business = st.session_state.get("business_profile", {})
    rows = st.session_state.get("approved_competitors", [])
    search = st.session_state.get("competitor_search_key")
    identity = (str(business.get("osm_id")), business.get("latitude"), business.get("longitude"))
    if not st.session_state.get("business_confirmed") or not business or not rows or not search or tuple(search[:3]) != identity:
        _empty_dashboard()
        return
    st.button("Back", icon=":material/arrow_back:",
              on_click=review_analysis_step,
              help="Go back one step to review your selected competitors.",
              key="dashboard_back_to_analysis")
    summary = summarize_selection(rows)
    with st.container(border=True, key="business_context"):
        left, right = st.columns([4,1], vertical_alignment="center")
        with left:
            st.subheader(business.get("name", "Your business"))
            st.caption(f"{search[3]}  ·  {search[4]} km radius  ·  {len(st.session_state.get('discovered_competitors', []))} discovered / {len(rows)} selected")
        with right:
            st.button("New analysis", on_click=navigate_to, args=("Automatic Analysis",), width="stretch", key="dashboard_new_analysis")
    area_based = business.get("resolution_status") == "area_center"
    if area_based:
        st.warning("Approximate area location. The store address is unverified; distances use the area centre.")
    notices = []
    if summary["unclassified"]:
        notices.append(f"{summary['unclassified']} selected businesses still need classification")
    if summary["limited"]:
        notices.append("map coverage is limited")
    if notices:
        st.caption("Availability: " + "; ".join(notices) + ". See business details below.")
    cards = [("Selected businesses", str(summary["selected"]), "selected"),
             ("Direct competitors", str(summary["direct"]) if summary["direct"] is not None else "Unavailable", "direct"),
             ("Indirect competitors", str(summary["indirect"]) if summary["indirect"] is not None else "Unavailable", "indirect"),
             ("Nearest business", f"{summary['nearest']:.2f} km" if summary["nearest"] is not None else "Unavailable", "nearest")]
    for column, (label, value, key) in zip(st.columns(4), cards):
        with column, st.container(border=True, key=f"kpi_{key}"):
            st.metric(label, value)
    if summary["unclassified"]:
        st.caption("Unavailable means classification has not completed, not that there are no competitors.")
    view = st.segmented_control("Explore your analysis", ["Overview", "Competitor list", "Map"], default="Overview", key="results_view") or "Overview"
    if view == "Overview":
        render_overview_charts(rows)
        left, right = st.columns([1.6,1], gap="medium")
        with left, st.container(border=True):
            _nearest_chart(rows)
        with right, st.container(border=True):
            _report_panel()
    elif view == "Competitor list":
        st.subheader("Selected businesses")
        frame = pd.DataFrame(rows).reindex(columns=["Name", "Category", "Distance (km)", "Classification", "Confidence"])
        st.dataframe(frame, hide_index=True, width="stretch", column_config={"Distance (km)": st.column_config.NumberColumn(format="%.2f km")})
        st.caption("Blue: Direct · Red: Indirect · Grey: unclassified or other. Review actual offerings before deciding relevance.")
        st.button("Review or change selection", on_click=navigate_to, args=("Competitor Analysis",), key="dashboard_edit_selection")
        export = [{key: json.dumps(value, ensure_ascii=False) if isinstance(value,(dict,list)) else value for key,value in row.items()} for row in rows]
        st.download_button("Download competitor list (CSV)", pd.DataFrame(export).to_csv(index=False).encode("utf-8-sig"), "CompeteRivio_Competitors.csv", "text/csv", key="dashboard_competitors_csv")
    else:
        st.subheader("Your business neighbourhood")
        positions = [{"lat":business.get("latitude"), "lon":business.get("longitude"), "color":"#10B981", "size":100}]
        positions += [{"lat":row.get("Latitude"),"lon":row.get("Longitude"),"color":CHART_COLORS.get(row.get("Classification"),"#94A3B8"),"size":60} for row in rows]
        data = pd.DataFrame(positions)
        data[["lat","lon"]] = data[["lat","lon"]].apply(pd.to_numeric,errors="coerce")
        data = data[data["lat"].between(-90,90) & data["lon"].between(-180,180)].dropna(subset=["lat","lon"])
        if not data.empty:
            st.map(data, color="color", size="size", height=440)
        else:
            st.info("Mapped coordinates are unavailable.")
        st.caption("Green: your business or approximate area centre · Blue: Direct · Red: Indirect · Grey: unclassified or other.")
    with st.expander("Business details and search notes"):
        st.write(business.get("location", "Address unavailable"))
        st.caption("Classifications are AI estimates and require review.")
        st.caption("Check the branch address. Distances are straight-line estimates, not travel distances. Discovery is not an exhaustive market survey.")
        for warning in st.session_state.get("automatic_warnings", []):
            st.write(warning)
