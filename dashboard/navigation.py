
import streamlit as st

PRIMARY_PAGES = ["Overview", "Automatic Analysis", "Analysis History"]
ADVANCED_PAGES = ["Business & Discovery", "Competitor Analysis", "Evidence & Scores", "Keyword Intelligence", "Marketing Intelligence", "AI Insights & Reports"]
PAGE_LABELS = {"Automatic Analysis": "New analysis", "Overview": "Dashboard", "Analysis History": "Saved reports"}


def navigate_to(page):
    st.session_state["main_navigation"] = page


def review_analysis_step(step="competitors"):
    st.session_state["_analysis_review_step"] = step
    navigate_to("Automatic Analysis")


def _choose_page(widget_key):
    if page := st.session_state.get(widget_key):
        navigate_to(page)


def sidebar_navigation():
    page = st.session_state.get("main_navigation", "Overview")
    if page not in PRIMARY_PAGES + ADVANCED_PAGES:
        page = "Overview"
    st.session_state["main_navigation"] = page
    st.session_state["primary_navigation"] = page if page in PRIMARY_PAGES else None
    st.session_state["advanced_navigation"] = page if page in ADVANCED_PAGES else None
    with st.sidebar:
        st.title("CompeteRivio AI")
        st.caption("LOCAL BUSINESS INTELLIGENCE")
        st.radio("Main menu", PRIMARY_PAGES, format_func=PAGE_LABELS.get, index=None,
                 key="primary_navigation", on_change=_choose_page, args=("primary_navigation",), label_visibility="collapsed")
        with st.expander("Analysis tools", expanded=page in ADVANCED_PAGES):
            st.caption("Optional tools for reviewing or improving your analysis.")
            st.selectbox("Open a tool", ADVANCED_PAGES, index=None, placeholder="Choose a tool",
                         key="advanced_navigation", on_change=_choose_page, args=("advanced_navigation",))
        with st.expander("Appearance"):
            st.caption("Choose Light or Dark from the top-right ⋮ menu → Theme.")
    mode = "Light" if st.context.theme.type == "light" else "Dark"
    st.session_state["appearance_mode"] = mode
    return page, mode
