
import html

import streamlit as st


def kpi_card(label, value, subtitle=""):
    safe_label = html.escape(str(label))
    safe_value = html.escape(str(value))
    safe_subtitle = html.escape(str(subtitle))

    st.markdown(
        f"""
        <div class="cr-card">
            <div class="cr-card-label">{safe_label}</div>
            <div class="cr-card-value">{safe_value}</div>
            <div class="cr-card-label">{safe_subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
