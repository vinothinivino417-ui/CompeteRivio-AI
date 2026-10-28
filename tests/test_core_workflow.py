import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from dashboard.competitor_discovery import process_competitors
from services.candidate_rules import is_directory
from services.competitor_selection import add_competitor, remove_competitor
from services.competitor_evidence import competitor_id
from services.automatic_analysis import resolve_automatic_profiles, run_automatic_analysis


class CandidateRulesTests(unittest.TestCase):
    def test_filter_dedupe_and_explainable_category_ranking(self):
        business = {"latitude": 13, "longitude": 80, "osm_id": 1, "osm_type": "node"}
        elements = [
            {"id": 1, "type": "node", "lat": 13, "lon": 80, "tags": {"name": "Own"}},
            {"id": 2, "type": "node", "lat": 13.001, "lon": 80, "tags": {"name": "Hospital Directory"}},
            {"id": 3, "type": "node", "lat": 13.001, "lon": 80, "tags": {"name": "Directory", "website": "https://www.justdial.com/hospital"}},
            {"id": 4, "type": "node", "lat": 13.001, "lon": 80, "tags": {"name": "Near cafe", "amenity": "cafe"}},
            {"id": 5, "type": "node", "lat": 13.01, "lon": 80, "tags": {"name": "Actual Hospital", "amenity": "hospital"}},
            {"id": 6, "type": "way", "center": {"lat": 13.01001, "lon": 80}, "tags": {"name": "Actual-Hospital", "amenity": "hospital"}},
            {"id": 7, "type": "node", "lat": float("nan"), "lon": 80, "tags": {"name": "Bad coordinates"}},
        ]
        rows = process_competitors(elements, business, "Hospital")
        self.assertEqual([row["Name"] for row in rows], ["Actual Hospital", "Near cafe"])
        self.assertEqual(rows[0]["Search prominence"], "Unavailable")
        self.assertIn("Processed at (UTC)", rows[0])
        self.assertIn("70", rows[0]["Relevance reason"])

    def test_directory_host_not_substring_matching(self):
        self.assertTrue(is_directory("Listing", "https://listings.justdial.com/item"))
        self.assertFalse(is_directory("Hospital", "https://justdial.com.example.org"))


class CompetitorOverridesTests(unittest.TestCase):
    def setUp(self):
        self.state = {"business_confirmed": True,
                      "business_profile": {"name": "Own", "osm_id": 1, "osm_type": "node", "latitude": 13., "longitude": 80.},
                      "competitor_search_key": ("1", 13., 80., "Hospital", 3),
                      "discovered_competitors": [], "approved_competitors": [],
                      "ai_insights_report": "Old report", "ai_insights_input": "Old signature", "analysis_history": [{"id": "keep"}]}

    def add(self, **kwargs):
        values = dict(name="Added hospital", category="Hospital", latitude=13.001, longitude=80, address="Test street")
        return add_competitor(self.state, **{**values, **kwargs})

    def test_add_remove_invalidates_current_report_preserves_history(self):
        row = self.add()
        self.assertEqual(row["Classification"], "Not classified")
        self.assertEqual(len(self.state["approved_competitors"]), 1)
        self.assertNotIn("ai_insights_report", self.state)
        remove_competitor(self.state, competitor_id(row))
        self.assertEqual(self.state["approved_competitors"], [])
        self.assertEqual(len(self.state["discovered_competitors"]), 1)
        self.assertEqual(self.state["analysis_history"], [{"id": "keep"}])

    def test_duplicates_and_self_rejected_without_changes(self):
        self.add()
        with self.assertRaises(ValueError):
            self.add(name="Added-Hospital", latitude=13.00101)
        with self.assertRaises(ValueError):
            self.add(name="Own", latitude=13.)
        self.assertEqual(len(self.state["approved_competitors"]), 1)

    def test_invalid_inputs_do_not_mutate_state(self):
        for kwargs in ({"latitude": float("inf")}, {"latitude": ""}, {"website": "javascript:alert(1)"}, {"website": "https://user:pass@example.com"}, {"name": "Hospital Directory"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.add(**kwargs)
        self.assertEqual(self.state["ai_insights_report"], "Old report")
        self.assertEqual(self.state["discovered_competitors"], [])

    def test_wrong_business_search_blocked(self):
        self.state["business_profile"]["osm_id"] = 2
        with self.assertRaises(ValueError):
            self.add()

    def test_two_coordinate_only_entries_have_distinct_ids(self):
        first = self.add()
        second = self.add(name="Another hospital", latitude=13.002)
        self.assertNotEqual(competitor_id(first), competitor_id(second))

    def test_adding_during_pending_review_preserves_gate(self):
        self.state["competitor_selection_mode"] = "pending_review"
        self.add()
        self.assertEqual(self.state["competitor_selection_mode"], "pending_review")

    @patch("dashboard.competitor_management.search_business")
    def test_manual_coordinates_ui_add_and_remove_without_network(self, lookup):
        app = AppTest.from_string("from dashboard.competitor_management import render_competitor_management\nrender_competitor_management()")
        for key, value in self.state.items():
            app.session_state[key] = value
        app.run()
        self.assertFalse(app.exception)
        app.text_input(key="manual_competitor_name").set_value("New hospital")
        app.text_input(key="manual_competitor_address").set_value("Test street")
        app.text_input(key="manual_competitor_latitude").set_value("13.001")
        app.text_input(key="manual_competitor_longitude").set_value("80")
        app.button(key="manual_competitor_submit").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["approved_competitors"][0]["Name"], "New hospital")
        self.assertNotIn("ai_insights_report", app.session_state)
        lookup.assert_not_called()
        app.button(key="manual_remove_competitor").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["approved_competitors"], [])
        self.assertEqual(app.session_state["analysis_history"], [{"id": "keep"}])


class ProfileConfirmationTests(unittest.TestCase):
    @patch("services.automatic_analysis.find_area")
    @patch("services.automatic_analysis.search_business")
    def test_multiple_profiles_and_area_fallback(self, search, area):
        search.return_value = [{"name": "One", "lat": 13, "lon": 80}, {"name": "Two", "lat": 14, "lon": 80}]
        self.assertEqual(len(resolve_automatic_profiles("Shop", "City", "Hospital")), 2)
        area.assert_not_called()
        search.return_value = []
        area.return_value = [{"name": "Area", "lat": 13, "lon": 80, "extratags": {"website": "https://city.example"}}]
        profile = resolve_automatic_profiles("Missing shop", "City", "Hospital")[0]
        self.assertEqual(profile["resolution_status"], "area_center")
        self.assertEqual(profile["website"], "")

    @patch("services.automatic_analysis.search_business")
    @patch("services.automatic_analysis.fetch_nearby_businesses")
    @patch("services.automatic_analysis.classify_competitors_with_gemini")
    def test_confirmed_profile_is_not_looked_up_again_and_no_report_before_review(self, classify, fetch, search):
        profile = {"name": "Chosen", "location": "Chosen street", "industry": "Hospital", "latitude": 13., "longitude": 80., "osm_id": 1, "osm_type": "node", "resolution_status": "business_listing"}
        fetch.return_value = [{"id": 2, "type": "node", "lat": 13.001, "lon": 80, "tags": {"name": "Other"}}]
        classify.side_effect = lambda business, rows: [{**row, "Classification": "Direct"} for row in rows]
        state = {}
        run_automatic_analysis(state, "Input", "City", "Hospital", 3, include_websites=False, confirmed_profile=profile, prepare_report=False)
        search.assert_not_called()
        self.assertEqual(state["business_profile"]["name"], "Chosen")
        self.assertEqual(state["competitor_selection_mode"], "pending_review")
        self.assertNotIn("ai_insights_report", state)

    @patch("services.automatic_analysis.search_business")
    @patch("services.automatic_analysis.fetch_nearby_businesses")
    def test_ui_requires_area_acknowledgement_and_cancel_preserves_old_work(self, fetch, search):
        search.return_value = []
        with patch("services.automatic_analysis.find_area", return_value=[{"lat": 13, "lon": 80, "display_name": "Approximate area"}]):
            app = AppTest.from_file(str(Path(__file__).with_name("automatic_analysis_app.py"))).run()
            app.text_input[0].set_value("Missing shop")
            app.text_input[1].set_value("City")
            next(b for b in app.button if b.label == "Find business profile").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key="auto_confirm_profile").disabled)
            fetch.assert_not_called()
            app.button(key="auto_cancel_profile").click().run()
            self.assertFalse(app.exception)
            self.assertNotIn("_pending_analysis", app.session_state)
