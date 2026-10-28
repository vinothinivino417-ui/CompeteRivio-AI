from pathlib import Path
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from services.analysis_history import archive_current_analysis
from dashboard.history import local_time
from history_fixtures import make_state, sign_state


class HistoryPageTests(unittest.TestCase):
    def test_restore_preview_and_apply_in_empty_history(self):
        saved = make_state()
        record = archive_current_analysis(saved)
        payload = json.dumps({"schema_version": 1, "analyses": [record]}).encode()
        app = self.make_app({"business_profile": {"name": "Current business"}})
        with patch("dashboard.history.st.file_uploader", return_value=BytesIO(payload)):
            app.run()
            self.assertFalse(app.exception, app.exception)
            self.assertNotIn("analysis_history", app.session_state)
            app.button(key="restore_history_backup").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(len(app.session_state["analysis_history"]), 1)
            self.assertEqual(app.session_state["business_profile"]["name"], "Current business")
            self.assertTrue(app.button(key="restore_history_backup").disabled)

    def test_saved_selection_comparison_keeps_current_workspace(self):
        state = make_state()
        first = archive_current_analysis(state)
        state["approved_competitors"] = [{**state["approved_competitors"][0], "OSM ID": "3", "Name": "Market B"}]
        sign_state(state)
        archive_current_analysis(state)
        app = self.make_app(state).run()
        self.assertFalse(app.exception, app.exception)
        app.selectbox(key="history_comparison_run").select(first["id"]).run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.metric[0].value, "1")
        self.assertEqual(app.metric[1].value, "1")
        self.assertEqual(app.session_state["approved_competitors"][0]["Name"], "Market B")

    def make_app(self, state):
        app = AppTest.from_file(str(Path(__file__).with_name("history_app.py")), default_timeout=30)
        for key, value in state.items():
            app.session_state[key] = value
        return app

    def test_viewing_old_run_does_not_change_current_workspace(self):
        state = make_state()
        first = archive_current_analysis(state)
        state["business_profile"]["name"] = "Another store"
        state["ai_insights_report"] = "# Another store report"
        sign_state(state)
        archive_current_analysis(state)
        app = self.make_app(state).run()
        self.assertFalse(app.exception, app.exception)
        app.selectbox(key="history_selected_run").select(first["id"]).run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["business_profile"]["name"], "Another store")
        self.assertTrue(any("DMart report" in item.value for item in app.markdown))
        app.button(key="remove_history_run").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.session_state["analysis_history"]), 1)
        self.assertEqual(app.session_state["business_profile"]["name"], "Another store")

    def test_empty_history_explains_how_to_save(self):
        app = self.make_app({}).run()
        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any("No saved analyses yet" in item.value for item in app.info))

    def test_save_time_is_displayed_in_india_timezone(self):
        self.assertIn("19:30:00 IST", local_time("2026-10-25T14:00:00+00:00"))
