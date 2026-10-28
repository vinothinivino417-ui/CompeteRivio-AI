import unittest
from unittest.mock import Mock, patch

from services.geocoding import search_places


class GeocodingTests(unittest.TestCase):
    def setUp(self):
        search_places.clear()
        self.addCleanup(search_places.clear)

    def test_identical_query_is_cached(self):
        response = Mock()
        response.json.return_value = [{"name": "Velachery"}]
        with patch("services.geocoding.requests.get", return_value=response) as request, patch("services.geocoding._last_request", 0):
            self.assertEqual(search_places({"q": "Velachery"}), search_places({"q": "Velachery"}))
        request.assert_called_once()

    def test_distinct_requests_are_rate_limited(self):
        response = Mock()
        response.json.return_value = []
        with patch("services.geocoding.requests.get", return_value=response), patch("services.geocoding._last_request", 0), patch("services.geocoding.time.monotonic", side_effect=[10.0, 10.0, 10.2, 11.05]), patch("services.geocoding.time.sleep") as sleep:
            search_places({"q": "Query one"})
            search_places({"q": "Query two"})
        self.assertAlmostEqual(sleep.call_args.args[0], 0.85)

    def test_invalid_response_is_rejected(self):
        response = Mock()
        response.json.return_value = {"error": "Bad response"}
        with patch("services.geocoding.requests.get", return_value=response), patch("services.geocoding._last_request", 0):
            with self.assertRaises(ValueError):
                search_places({"q": "Example"})


if __name__ == "__main__":
    unittest.main()
