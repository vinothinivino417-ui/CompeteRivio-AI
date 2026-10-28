from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from history_fixtures import make_state


class SimplifiedDashboardTests(unittest.TestCase):
    def test_fresh_install_opens_dashboard_with_a_clear_start_action(self):
        app = self.app()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["main_navigation"], "Overview")
        self.assertEqual(len(app.get("plotly_chart")), 0)
        app.button(key="dashboard_get_started").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["main_navigation"], "Automatic Analysis")
        self.assertEqual(app.text_input[0].label, "Business name")

    def app(self, state=None):
        app = AppTest.from_file(str(Path(__file__).with_name("saved_search_app.py")), default_timeout=30)
        for key, value in (state or {}).items():
            app.session_state[key] = value
        return app.run()

    def test_main_menu_has_three_choices_and_advanced_roundtrip_works(self):
        app = self.app()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.radio(key="primary_navigation").options, ["Dashboard", "New analysis", "Saved reports"])
        app.selectbox(key="advanced_navigation").select("Evidence & Scores").run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["main_navigation"], "Evidence & Scores")
        self.assertIsNone(app.radio(key="primary_navigation").value)
        app.radio(key="primary_navigation").set_value("Automatic Analysis").run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["main_navigation"], "Automatic Analysis")
        self.assertIsNone(app.selectbox(key="advanced_navigation").value)

    def test_report_is_collapsed_and_results_button_opens_separate_page(self):
        state = make_state()
        state["main_navigation"] = "Automatic Analysis"
        state["approved_competitors"][0]["Classification"] = "Not classified"
        from history_fixtures import sign_state
        sign_state(state)
        app = self.app(state)
        self.assertFalse(app.exception, app.exception)
        preview = next(item for item in app.expander if item.label == "Preview report")
        self.assertFalse(preview.proto.expanded)
        self.assertTrue(any("not classified yet" in item.value for item in app.warning))
        self.assertEqual(len(app.get("plotly_chart")), 0)
        app.button(key="auto_view_results").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["main_navigation"], "Overview")
        self.assertEqual(app.radio(key="primary_navigation").value, "Overview")
        self.assertEqual(len(app.get("plotly_chart")), 3)

    def test_results_show_one_section_at_a_time(self):
        state = {**make_state(), "main_navigation": "Overview"}
        app = self.app(state)
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 3)
        app.segmented_control(key="results_view").set_value("Competitor list").run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 0)
        app.segmented_control(key="results_view").set_value("Map").run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 0)

    def test_unclassified_selection_does_not_claim_zero_direct_competitors(self):
        state = {**make_state(), "main_navigation": "Overview", "results_view": "Competitor list"}
        state["approved_competitors"][0]["Classification"] = "Not classified"
        app = self.app(state)
        self.assertFalse(app.exception, app.exception)
        metrics = {item.label: item.value for item in app.metric}
        self.assertEqual(metrics["Direct competitors"], "Unavailable")
        self.assertEqual(metrics["Indirect competitors"], "Unavailable")

    def test_classified_selection_still_reports_observed_counts(self):
        state = {**make_state(), "main_navigation": "Overview", "results_view": "Competitor list"}
        app = self.app(state)
        self.assertFalse(app.exception, app.exception)
        metrics = {item.label: item.value for item in app.metric}
        self.assertEqual(metrics["Direct competitors"], "1")
        self.assertEqual(metrics["Indirect competitors"], "0")
