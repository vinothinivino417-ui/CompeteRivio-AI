import unittest

from services.competitor_evidence import evidence_scope
from services.marketing_analysis import observed_ad_count, build_marketing_evidence


class MarketingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.business = {"name": "DMart", "osm_id": 1}
        self.competitors = [{"Name": "Market A", "OSM ID": "2", "OSM Type": "node"}]
        self.observation = {"Active Ads": 0, "Source": "Public ad-library observation", "Observed On": "2000-01-01"}

    def test_zero_is_preserved_and_unknown_is_not_zero(self):
        rows = build_marketing_evidence(self.business, self.competitors, {evidence_scope(self.business): {"business": self.observation}})
        self.assertEqual(rows[0]["Active Ads"], 0)
        self.assertIsNone(rows[1]["Active Ads"])
        self.assertEqual(rows[0]["Ad-count source"], self.observation["Source"])
        self.assertEqual(rows[0]["Ad-count observed on"], "2000-01-01")

    def test_invalid_counts_and_missing_provenance_are_unavailable(self):
        for value in [-1, float("nan"), 1.5, True, "bad"]:
            self.assertIsNone(observed_ad_count({**self.observation, "Active Ads": value}))
        for value in [{**self.observation, "Source": ""}, {**self.observation, "Observed On": ""}, {**self.observation, "Observed On": "2999-01-01"}]:
            self.assertIsNone(observed_ad_count(value))

    def test_evidence_does_not_leak_between_businesses(self):
        saved = {evidence_scope({"name": "Other"}): {"business": self.observation}}
        rows = build_marketing_evidence(self.business, self.competitors, saved)
        self.assertTrue(all(row["Active Ads"] is None for row in rows))

    def test_only_available_and_sourced_website_text_is_used(self):
        self.business["Website analysis"] = {"Status": "Available", "Source URL": "https://example.org", "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00", "Page title": "Observed webpage title", "Description": "Observed description", "Headings": ["Groceries"]}
        self.competitors[0]["Website analysis"] = {"Status": "Blocked", "Page title": "Do not use this"}
        rows = build_marketing_evidence(self.business, self.competitors, {})
        self.assertTrue(rows[0]["Website evidence usable"])
        self.assertEqual(rows[0]["Webpage title"], "Observed webpage title")
        self.assertFalse(rows[1]["Website evidence usable"])
        self.assertEqual(rows[1]["Webpage title"], "")
        self.assertIsNone(rows[0]["Active Ads"])
        self.assertNotIn("Trend", rows[0])

    def test_duplicate_names_have_distinct_chart_labels(self):
        rows = build_marketing_evidence(self.business, self.competitors * 2, {})
        self.assertEqual(len({row["Label"] for row in rows}), len(rows))
