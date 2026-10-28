from dashboard.navigation import sidebar_navigation
from dashboard.history import render_history
from dashboard.automatic_analysis import render_automatic_analysis
from dashboard.overview import render_overview

page, _ = sidebar_navigation()
if page == "Analysis History":
    render_history()
elif page == "Automatic Analysis":
    render_automatic_analysis()
elif page == "Overview":
    render_overview()
