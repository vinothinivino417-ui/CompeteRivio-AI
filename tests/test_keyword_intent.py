import unittest

from services.keyword_intent import estimate_intent
from services.keyword_analysis import build_keyword_analysis
from services.report_content import build_grounded_report


class KeywordIntentTests(unittest.TestCase):
    def intent(self, term):
        return estimate_intent(term, ["Apollo Pharmacy", "DMart"], ["Velachery, Chennai, Tamil Nadu"])["Intent group (estimate)"]

    def test_four_groups_and_unknown(self):
        for term, expected in (("apollo", "Branded"), ("D Mart", "Branded"), ("home delivery", "Service"),
                               ("Velachery", "Location"), ("Chennai pharmacy", "Location"),
                               ("medicine benefits", "Informational"), ("unexplainedword", "Unclassified")):
            with self.subTest(term=term):
                self.assertEqual(self.intent(term), expected)

    def test_no_brand_substring_false_positive(self):
        self.assertEqual(self.intent("apollonian"), "Unclassified")

    def test_generic_industry_is_not_automatically_branded(self):
        self.assertEqual(self.intent("pharmacy"), "Service")

    def test_priority_and_geography_in_brand_name(self):
        self.assertEqual(self.intent("why apollo"), "Informational")
        group = estimate_intent("velachery", ["Apollo Velachery"], ["Velachery Chennai"])
        self.assertEqual(group["Intent group (estimate)"], "Location")

    def test_missing_pages_do_not_get_zero_clusters(self):
        result = build_keyword_analysis({"name": "Shop"}, [{"Name": "Other"}])
        self.assertEqual(result["Intent counts"], [])

    def test_store_name_in_full_address_does_not_become_geographic(self):
        result = estimate_intent("apollo delivery", ["Apollo Pharmacy"], ["Apollo Pharmacy, Velachery, Chennai"])
        self.assertEqual(result["Intent group (estimate)"], "Branded")

    def test_cluster_membership_and_provenance(self):
        audit = {"Status": "Available", "Source URL": "https://example.org", "Retrieved at (UTC)": "2026-10-27T08:00:00+00:00", "On-page keyword candidates": ["apollo", "delivery", "chennai", "guide", "unexplainedword"]}
        result = build_keyword_analysis({"name": "Apollo Pharmacy", "location": "Chennai", "Website analysis": audit}, [{"Name": "Unknown"}])
        groups = result["Entities"][0]["Intent groups"]
        self.assertEqual(sum(map(len, groups.values())), 5)
        self.assertEqual(len(result["Intent counts"]), 5)
        self.assertTrue(all(row["Source URL"] == "https://example.org" and "Intent reason" in row for row in result["Observations"]))
        report = build_grounded_report({"name": "Apollo Pharmacy", "Website analysis": audit}, [])
        self.assertIn("Estimated intent clusters", report)
        self.assertIn("Source: https://example.org", report)
        self.assertIn("not observed search behaviour", report)
