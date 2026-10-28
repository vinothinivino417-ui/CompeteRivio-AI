import json
import os
import unittest
from unittest.mock import Mock, patch

import requests

from services.google_places import fetch_google_rating, FIELDS
from services.workspace_storage import snapshot


class GooglePlacesTests(unittest.TestCase):
    def setUp(self):
        self.key = patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-only-key"})
        self.key.start()
        self.addCleanup(self.key.stop)
        self.session = patch("services.google_places.requests.Session").start()
        self.addCleanup(patch.stopall)
        self.request = self.session.return_value.__enter__.return_value.post
        self.response = Mock(status_code=200)
        self.request.return_value = self.response
        self.place = {"id": "test-place-id", "displayName": {"text": "DMart"},
                      "formattedAddress": "Test address", "location": {"latitude": 13, "longitude": 80},
                      "rating": 4.2, "userRatingCount": 123,
                      "attributions": [{"provider": "Test provider"}]}
        self.response.json.return_value = {"places": [self.place]}

    def fetch(self):
        return fetch_google_rating("D Mart", 13, 80)

    def test_missing_key_makes_no_request(self):
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
            self.assertEqual(self.fetch()["Status"], "Not configured")
        self.request.assert_not_called()

    def test_matched_data_and_restricted_request(self):
        result = self.fetch()
        self.assertEqual(result["Rating"], 4.2)
        self.assertEqual(result["Review Count"], 123)
        self.assertIn("test-place-id", result["Google Maps URL"])
        kwargs = self.request.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-Goog-FieldMask"], FIELDS)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertNotIn("test-only-key", json.dumps(result))

    def test_missing_is_not_zero(self):
        self.place.pop("rating")
        self.place["userRatingCount"] = 0
        result = self.fetch()
        self.assertIsNone(result["Rating"])
        self.assertEqual(result["Review Count"], 0)

    def test_wrong_name_or_distant_branch_rejected(self):
        self.place["displayName"]["text"] = "Other shop"
        self.assertEqual(self.fetch()["Status"], "Needs review")
        self.place["displayName"]["text"] = "DMart"
        self.place["location"]["latitude"] = 14
        self.assertEqual(self.fetch()["Status"], "Needs review")

    def test_ambiguous_branches_rejected(self):
        self.response.json.return_value = {"places": [self.place, {**self.place, "id": "another"}]}
        self.assertEqual(self.fetch()["Status"], "Needs review")

    def test_invalid_coordinates_make_no_request(self):
        for latitude in (None, True, float("nan"), 100):
            with self.subTest(latitude=latitude):
                self.assertEqual(fetch_google_rating("DMart", latitude, 80)["Status"], "Unavailable")
        self.request.assert_not_called()

    def test_provider_failures_do_not_leak_details(self):
        for status in (400, 401, 403, 429, 503):
            self.response.status_code = status
            self.response.text = "test-only-key"
            result = self.fetch()
            self.assertEqual(result["Status"], "Unavailable")
            self.assertNotIn("test-only-key", json.dumps(result))

    def test_timeout_is_safe(self):
        self.request.side_effect = requests.Timeout("test-only-key")
        result = self.fetch()
        self.assertEqual(result["Status"], "Unavailable")
        self.assertNotIn("test-only-key", json.dumps(result))

    def test_invalid_measurements_rejected(self):
        for rating in (True, float("nan"), 6, "4.2"):
            self.place["rating"] = rating
            self.assertEqual(self.fetch()["Status"], "Unavailable")

    def test_google_session_results_not_persisted(self):
        self.assertNotIn("_google_live_ratings", snapshot({"_google_live_ratings": {"rows": [self.fetch()]}}))
