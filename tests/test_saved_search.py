import copy
import unittest

from services.saved_search import saved_search_inputs, stage_saved_search
from services.analysis_history import archive_current_analysis
from history_fixtures import make_state


class SavedSearchTests(unittest.TestCase):
    def setUp(self):
        self.state = make_state()
        self.snapshot = archive_current_analysis(self.state)["snapshot"]

    def test_loads_search_settings_without_changing_active_or_saved_results(self):
        before = copy.deepcopy(self.state)
        self.snapshot["business"]["website"] = "https://example.org"
        result = stage_saved_search(self.state, self.snapshot, ["Supermarket"])
        self.assertEqual(result, {"name": "DMart", "location": "Velachery, Chennai", "category": "Supermarket", "radius": 3, "website": "https://example.org", "include_websites": True})
        self.assertEqual(self.state["main_navigation"], "Automatic Analysis")
        for key, value in before.items():
            self.assertEqual(self.state[key], value)
        revision = self.state["_automatic_form_revision"]
        stage_saved_search(self.state, self.snapshot, ["Supermarket"])
        self.assertNotEqual(self.state["_automatic_form_revision"], revision)

    def test_invalid_search_leaves_state_unchanged(self):
        for field, value in [("category", ""), ("category", "x" * 101), ("category", []), ("radius_km", 0), ("radius_km", 21), ("radius_km", 2.5), ("radius_km", True), ("radius_km", float("nan"))]:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot[field] = value
            before = copy.deepcopy(self.state)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                stage_saved_search(self.state, snapshot, ["Supermarket"])
            self.assertEqual(before, self.state)

    def test_missing_name_location_and_invalid_website_are_rejected(self):
        for key, value in [("name", ""), ("location", None), ("website", ["invalid"])]:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot["business"][key] = value
            with self.assertRaises(ValueError):
                saved_search_inputs(snapshot, ["Supermarket"])
