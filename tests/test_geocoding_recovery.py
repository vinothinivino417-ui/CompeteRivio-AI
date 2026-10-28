from pathlib import Path
import unittest
from unittest.mock import patch, Mock

import requests
from streamlit.testing.v1 import AppTest

from services.alternate_geocoding import find_area_alternate
from services.business_profiles import saved_profile_choice
from services.automatic_analysis import resolve_automatic_profiles


class GeocodingRecoveryTests(unittest.TestCase):
    def setUp(self):
        find_area_alternate.clear()
        self.addCleanup(find_area_alternate.clear)
        self.profile = {"name": "Brandmonk Academy", "location": "Valasaravakkam, Chennai", "latitude": 13.04, "longitude": 80.18, "industry": "Training Academy", "source": "OpenStreetMap", "resolution_status": "area_center"}

    @patch("services.alternate_geocoding.requests.get")
    def test_photon_rejects_road_and_preserves_locality_provenance(self, get):
        def feature(key, value, name, coords):
            return {"properties": {"name": name, "osm_key": key, "osm_value": value, "countrycode": "IN", "country": "India"}, "geometry": {"type": "Point", "coordinates": coords}}
        response = Mock()
        response.json.return_value = {"features": [feature("highway", "construction", "Nearby road", [80, 13]), feature("place", "suburb", "Valasaravakkam", [80.18, 13.04]), feature("place", "city", "Invalid", [80, 999])]}
        get.return_value = response
        rows = find_area_alternate("Valasaravakkam, Chennai, India")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["lat"], "13.04")
        self.assertEqual(rows[0]["_geocoder"], "Photon / OpenStreetMap")
        get.assert_called_once()

    @patch("services.automatic_analysis.find_area_alternate")
    @patch("services.automatic_analysis.search_business", side_effect=requests.Timeout("timeout"))
    def test_primary_failure_uses_alternate_once_without_second_nominatim_request(self, search, alternate):
        alternate.return_value = [{"name": "Area", "lat": "13.04", "lon": "80.18", "display_name": "Valasaravakkam", "_geocoder": "Photon / OpenStreetMap"}]
        with patch("services.automatic_analysis.find_area") as primary_area:
            profile = resolve_automatic_profiles("Brandmonk Academy", "Valasaravakkam Chennai", "Training Academy")[0]
        primary_area.assert_not_called()
        alternate.assert_called_once()
        self.assertEqual(profile["resolution_status"], "area_center")
        self.assertIn("Photon", profile["source"])

    def test_saved_location_never_reused_for_another_business(self):
        state = {"business_confirmed": True, "business_profile": self.profile}
        self.assertIsNone(saved_profile_choice(state, {"name": "Different", "category": "Training Academy"}))
        self.assertIsNotNone(saved_profile_choice(state, {"name": "Brand Monk Academy", "category": "Training Academy"}))

    @patch("dashboard.automatic_analysis.resolve_automatic_profiles", side_effect=requests.Timeout("raw internal timeout"))
    def test_ui_saved_location_recovery_requires_confirmation(self, resolve):
        app = AppTest.from_file(str(Path(__file__).with_name("automatic_analysis_app.py")))
        app.session_state["business_profile"] = self.profile
        app.session_state["business_confirmed"] = True
        app.run()
        app.text_input[0].set_value("Brandmonk Academy")
        app.text_input[1].set_value("Valasaravakkam Chennai")
        next(b for b in app.button if b.label == "Find business profile").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any("location service did not respond" in w.value for w in app.warning))
        app.button(key="reuse_saved_profile").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertTrue(app.button(key="auto_confirm_profile").disabled)
        resolve.assert_called_once()
