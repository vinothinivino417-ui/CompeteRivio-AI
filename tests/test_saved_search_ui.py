from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from history_fixtures import make_state
from services.analysis_history import archive_current_analysis


class SavedSearchUITests(unittest.TestCase):
    def test_history_button_replaces_prior_form_draft_without_running_search(self):
        state = make_state()
        state["main_navigation"] = "Automatic Analysis"
        archive_current_analysis(state)
        state["automatic_inputs"] = {"name": "Old draft", "location": "Old area", "category": "Hospital", "radius": 2}
        app = AppTest.from_file(str(Path(__file__).with_name("saved_search_app.py")), default_timeout=30)
        for key, value in state.items():
            app.session_state[key] = value
        with patch("dashboard.automatic_analysis.run_automatic_analysis") as search, patch("dashboard.automatic_analysis.generate_saved_report") as report:
            app.run()
            self.assertFalse(app.exception, app.exception)
            app.text_input[0].set_value("Unsubmitted draft").run()
            app.radio(key="primary_navigation").set_value("Analysis History").run()
            self.assertFalse(app.exception, app.exception)
            app.button(key="reuse_history_search").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.session_state["main_navigation"], "Automatic Analysis")
            self.assertEqual(app.text_input[0].value, "DMart")
            self.assertEqual(app.text_input[1].value, "Velachery, Chennai")
            self.assertEqual(app.selectbox[0].value, "Supermarket")
            self.assertEqual(app.slider[0].value, 3)
            self.assertEqual(app.session_state["ai_insights_report"], state["ai_insights_report"])
            self.assertEqual(len(app.session_state["analysis_history"]), 1)
            search.assert_not_called()
            report.assert_not_called()
