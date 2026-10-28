from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from services.candidate_rules import CATEGORY_TAGS, category_filters, valid_industry, suggested_category
from services.automatic_analysis import run_automatic_analysis
from services.saved_search import saved_search_inputs
from services.competitor_selection import add_competitor
from dashboard.competitor_discovery import fetch_nearby_businesses


class IndustryPickerTests(unittest.TestCase):
    def test_common_industries_and_custom_validation(self):
        self.assertGreaterEqual(len(CATEGORY_TAGS), 60)
        for name in ("Training Academy", "Digital Marketing Agency", "Gym / Fitness Centre", "Hair Salon", "Software Company", "Bank", "Grocery Store"):
            self.assertTrue(category_filters(name))
        self.assertTrue(valid_industry("Handmade Toy Studio"))
        self.assertFalse(valid_industry(""))
        self.assertFalse(valid_industry("x" * 101))
        self.assertFalse(valid_industry("bad\ncategory"))
        self.assertEqual(suggested_category("Handmade Toy Studio"), "Handmade Toy Studio")

    @patch("dashboard.competitor_discovery.requests.post")
    def test_custom_industry_never_interpolated_into_map_query(self, request):
        fetch_nearby_businesses.clear()
        self.addCleanup(fetch_nearby_businesses.clear)
        self.assertEqual(fetch_nearby_businesses(13, 80, 'Custom["injected"]', 3000), [])
        request.assert_not_called()

    def test_custom_reuse_and_manual_competitor(self):
        profile = {"name": "Own", "location": "City", "latitude": 13., "longitude": 80., "osm_id": 1, "osm_type": "node", "industry": "Handmade Toy Studio"}
        snapshot = {"business": profile, "category": "Handmade Toy Studio", "radius_km": 3}
        self.assertEqual(saved_search_inputs(snapshot, CATEGORY_TAGS)["category"], "Handmade Toy Studio")
        state = {"business_profile": profile, "business_confirmed": True, "competitor_search_key": ("1", 13., 80., "Handmade Toy Studio", 3)}
        row = add_competitor(state, "Another studio", "Handmade Toy Studio", 13.001, 80, "Street")
        self.assertEqual(row["Category"], "Handmade Toy Studio")
        self.assertIn("proximity only", row["Relevance reason"])

    def test_custom_industry_keeps_label_and_opens_manual_review(self):
        profile = {"name": "Own", "location": "City", "latitude": 13., "longitude": 80., "osm_id": 1, "osm_type": "node", "industry": "Handmade Toy Studio"}
        state = {}
        run_automatic_analysis(state, "Own", "City", "Handmade Toy Studio", 3, confirmed_profile=profile, prepare_report=False, include_websites=False)
        self.assertEqual(state["competitor_selection_mode"], "pending_review")
        self.assertEqual(state["business_profile"]["industry"], "Handmade Toy Studio")
        self.assertIn("custom industry", state["automatic_warnings"][-1])

    def test_dropdown_available_on_both_entry_screens(self):
        for source in ("from dashboard.automatic_analysis import render_automatic_analysis\nrender_automatic_analysis()",
                       "from dashboard.business_discovery import render_business_discovery\nrender_business_discovery()"):
            app = AppTest.from_string(source).run()
            self.assertFalse(app.exception, app.exception)
            picker = next(s for s in app.selectbox if "Industry" in s.label)
            self.assertIn("Training Academy", picker.options)
            self.assertTrue(picker.proto.accept_new_options)
            picker.set_value("Training Academy").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(next(s for s in app.selectbox if "Industry" in s.label).value, "Training Academy")

    def test_custom_industry_roundtrip_not_replaced_by_hospital(self):
        app = AppTest.from_string('from dashboard.industry_picker import industry_picker\nindustry_picker("Industry", "industry", "Handmade Toy Studio")').run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.selectbox[0].value, "Handmade Toy Studio")
