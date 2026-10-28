
import streamlit as st

CHART_COLORS = {"Direct": "#2563EB", "Indirect": "#DC2626", "Irrelevant": "#64748B", "Not classified": "#94A3B8"}

# CompeteRivio AI - Dark and Light themes

THEMES = {
    "Dark": {
        "background": "#0B1625",
        "surface": "#15263B",
        "text": "#F3F7FA",
        "muted": "#A9BDCD",
        "accent": "#10B981",
        "border": "#30445A",
        "input_bg": "#15263B",
    },
    "Light": {
        "background": "#F8F9F6",
        "surface": "#FFFFFF",
        "text": "#24332D",
        "muted": "#52665B",
        "accent": "#047857",
        "border": "#DCE7DF",
        "input_bg": "#FFFFFF",
    },
}


def apply_theme(mode="Dark"):
    """Return chart colours; Streamlit owns all native widget styling."""
    # Inherit the native text colour so captions stay legible in either mode.
    st.html("<style>[data-testid='stCaptionContainer'] {color: inherit !important;} [data-testid='stCaptionContainer'] p {color: inherit !important; opacity: .85;}</style>")
    st.html("""<style>
      .block-container {max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem;}
      h1 {letter-spacing: -.035em; font-size: 2.1rem !important; font-weight: 750 !important;}
      h3 {letter-spacing: -.02em; font-size: 1.15rem !important; line-height: 1.4;}
      .st-key-business_context h3 {font-size: 1.4rem !important;}
      [data-testid='stVerticalBlockBorderWrapper'] {border-radius: 14px;}
      .st-key-business_context, .st-key-welcome_card {background: color-mix(in srgb, currentColor 3%, transparent);}
      .st-key-kpi_selected, .st-key-kpi_direct {border-top: 3px solid #2563EB !important;}
      .st-key-kpi_indirect {border-top: 3px solid #EF4444 !important;}
      .st-key-kpi_nearest {border-top: 3px solid #10B981 !important;}
      [data-testid='stMetricValue'] {font-size: clamp(1.35rem, 2vw, 2rem); font-weight: 650;}
      [data-testid='stForm'] {border-radius: 14px;}
      [data-testid='stSidebar'] [data-testid='stRadio'] label {padding: .35rem .25rem;}
      button {transition: box-shadow .18s ease;}
      button:hover {box-shadow: 0 3px 12px #00000012;}
      @media (max-width: 700px) {.block-container {padding-top: 1rem;}}
    </style>""")
    return THEMES.get(mode, THEMES["Dark"])
