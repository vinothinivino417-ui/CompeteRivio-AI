import unittest
from unittest.mock import Mock, patch
import requests

from dashboard.competitor_discovery import fetch_nearby_businesses, OVERPASS_ENDPOINTS
from services.geocoding import find_nearby_places


class DiscoveryFallbackTests(unittest.TestCase):
    def setUp(self):
        fetch_nearby_businesses.clear()
        self.addCleanup(fetch_nearby_businesses.clear)

    def test_primary_success_does_not_call_fallback(self):
        response = Mock()
        response.json.return_value = {"elements": [{"id": 1}]}
        with patch("dashboard.competitor_discovery.requests.post", return_value=response), patch("dashboard.competitor_discovery.find_nearby_places") as fallback:
            self.assertEqual(fetch_nearby_businesses(13, 80, "Supermarket", 3000), [{"id": 1}])
        fallback.assert_not_called()

    def test_primary_timeout_uses_bounded_fallback_without_trying_every_server(self):
        rows = [{"id": 2, "discovery_source": "OpenStreetMap nearby search (limited best matches)"}]
        with patch("dashboard.competitor_discovery.requests.post", side_effect=requests.Timeout("Timeout")) as primary, patch("dashboard.competitor_discovery.find_nearby_places", return_value=rows) as fallback:
            self.assertEqual(fetch_nearby_businesses(13, 80, "Supermarket", 3000), rows)
        self.assertEqual(primary.call_count, 1)
        fallback.assert_called_once_with(13, 80, "shop", "supermarket", 3000)

    def test_empty_fallback_keeps_trying_remaining_servers(self):
        with patch("dashboard.competitor_discovery.requests.post", side_effect=requests.Timeout("Timeout")) as primary, patch("dashboard.competitor_discovery.find_nearby_places", return_value=[]) as fallback:
            with self.assertRaises(requests.RequestException):
                fetch_nearby_businesses(13, 80, "Supermarket", 3000)
        self.assertEqual(primary.call_count, len(OVERPASS_ENDPOINTS))
        self.assertEqual(fallback.call_count, 1)

    def test_partial_primary_response_does_not_become_a_success(self):
        response = Mock()
        response.json.return_value = {"elements": [], "remark": "runtime error"}
        with patch("dashboard.competitor_discovery.requests.post", return_value=response), patch("dashboard.competitor_discovery.find_nearby_places", return_value=[{"id": 2}]):
            self.assertEqual(fetch_nearby_businesses(13, 80, "Supermarket", 3000), [{"id": 2}])

    def test_fallback_filters_wrong_categories_and_outside_radius(self):
        valid = {"name": "Market", "osm_id": 1, "osm_type": "node", "lat": "13.001", "lon": "80", "category": "shop", "type": "supermarket"}
        rows = [valid, dict(valid, osm_id=2, category="amenity", type="clinic"), dict(valid, osm_id=3, lat="14"), dict(valid, osm_id=None)]
        with patch("services.geocoding.search_places", return_value=rows) as lookup:
            result = find_nearby_places(13, 80, "shop", "supermarket", 1000)
        self.assertEqual([row["id"] for row in result], [1])
        params = lookup.call_args.args[0]
        self.assertEqual(params["bounded"], 1)
        self.assertEqual(params["limit"], 20)
        self.assertIn("limited best matches", result[0]["discovery_source"])

    def test_academy_partial_fallback_survives_another_category_failure(self):
        rows = [{"id": 2, "discovery_source": "OpenStreetMap nearby search (limited best matches)"}]
        with patch("dashboard.competitor_discovery.requests.post", side_effect=requests.Timeout("Timeout")), patch("dashboard.competitor_discovery.find_nearby_places", side_effect=[rows, requests.Timeout("Timeout"), []]):
            self.assertEqual(fetch_nearby_businesses(13, 80, "Training Academy", 3000), rows)


if __name__ == "__main__":
    unittest.main()
