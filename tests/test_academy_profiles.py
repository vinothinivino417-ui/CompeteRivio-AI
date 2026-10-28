from pathlib import Path
import unittest
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest
from services.business_profiles import build_area_profile, confirm_business_profile
from services.candidate_rules import relevance_fields, category_filters
from services.automatic_analysis import run_automatic_analysis
from dashboard.competitor_discovery import fetch_nearby_businesses


class AcademyProfileTests(unittest.TestCase):
    def setUp(self):
        self.entered = {"name": "Brandmonk Academy", "location": "Valasaravakkam, Chennai", "industry": "education and training academy", "website": "https://brandmonkacademy.com"}
        self.area = {"lat": "13.04", "lon": "80.18", "display_name": "Valasaravakkam, Chennai, India"}

    def test_area_confirmation_clears_stale_pharmacy_results(self):
        state = {"business_profile": {"name": "MedPlus"}, "discovered_competitors": [{"Name": "Old pharmacy"}], "approved_competitors": [{"Name": "Old pharmacy"}], "competitor_search_key": ["old", 13, 80, "Pharmacy", 3], "ai_insights_report": "Old", "analysis_history": [{"id": "keep"}]}
        profile = build_area_profile(self.entered, self.area)
        confirm_business_profile(state, profile)
        self.assertEqual(state["competitor_category"], "Training Academy")
        self.assertEqual(state["business_profile"]["latitude"], 13.04)
        self.assertEqual(state["business_profile"]["resolution_status"], "area_center")
        self.assertNotIn("approved_competitors", state)
        self.assertNotIn("ai_insights_report", state)
        self.assertEqual(state["analysis_history"], [{"id": "keep"}])

    def test_invalid_location_not_confirmed(self):
        state = {"business_profile": {"name": "Keep"}}
        with self.assertRaises(ValueError):
            confirm_business_profile(state, self.entered)
        self.assertEqual(state["business_profile"]["name"], "Keep")

    def test_training_query_and_category_evidence(self):
        fetch_nearby_businesses.clear()
        self.addCleanup(fetch_nearby_businesses.clear)
        response = Mock()
        response.json.return_value = {"elements": []}
        with patch("dashboard.competitor_discovery.requests.post", return_value=response) as fetch:
            fetch_nearby_businesses(13, 80, "Training Academy", 3000)
        for key, value in category_filters("Training Academy"):
            self.assertIn(f'["{key}"="{value}"]', fetch.call_args.kwargs["data"]["data"])
            self.assertEqual(relevance_fields({key: value}, "Training Academy", 0)["Relevance score"], 100)

    @patch("services.automatic_analysis.fetch_nearby_businesses", return_value=[])
    @patch("services.automatic_analysis.classify_competitors_with_gemini")
    def test_sparse_map_still_allows_review_and_manual_add(self, classify, fetch):
        profile = build_area_profile({**self.entered, "industry": "Training Academy"}, self.area)
        state = {}
        run_automatic_analysis(state, profile["name"], profile["location"], "Training Academy", 3, confirmed_profile=profile, prepare_report=False, include_websites=False)
        self.assertEqual(state["competitor_selection_mode"], "pending_review")
        self.assertEqual(state["approved_competitors"], [])
        self.assertIn("No mapped competitors", state["automatic_warnings"][-1])
        classify.assert_not_called()

    @patch("dashboard.business_discovery.find_area")
    def test_ui_area_preview_requires_explicit_confirmation(self, find_area):
        find_area.return_value = [self.area]
        app = AppTest.from_string("from dashboard.business_discovery import render_business_discovery\nrender_business_discovery()")
        app.session_state["business_search_input"] = self.entered
        app.session_state["business_search_results"] = []
        app.run()
        app.button(key="find_manual_business_area").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertNotIn("business_profile", app.session_state)
        app.button(key="confirm_manual_business_area").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["business_profile"]["latitude"], 13.04)
        self.assertEqual(app.session_state["competitor_category"], "Training Academy")

    @patch("dashboard.automatic_analysis._run_confirmed_analysis")
    @patch("dashboard.competitor_discovery.fetch_nearby_businesses.clear")
    def test_retry_uses_confirmed_academy_not_stale_form_inputs(self, clear, run):
        profile = build_area_profile({**self.entered, "industry": "Training Academy"}, self.area)
        app = AppTest.from_string("from dashboard.automatic_analysis import render_automatic_analysis\nrender_automatic_analysis()")
        app.session_state["business_profile"] = profile
        app.session_state["business_confirmed"] = True
        app.session_state["competitor_selection_mode"] = "pending_review"
        app.session_state["competitor_search_key"] = ("None", profile["latitude"], profile["longitude"], "Training Academy", 5)
        app.session_state["automatic_inputs"] = {"name": "Old pharmacy", "category": "Pharmacy"}
        app.session_state["approved_competitors"] = []
        app.run()
        self.assertFalse(app.exception, app.exception)
        run.assert_not_called()
        app.button(key="auto_retry_discovery").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(run.call_args.args[0]["name"], "Brandmonk Academy")
        self.assertEqual(run.call_args.args[0]["category"], "Training Academy")
        self.assertEqual(run.call_args.args[0]["radius"], 5)
        clear.assert_called_once()
