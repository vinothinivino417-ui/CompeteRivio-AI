import json
import unittest
from unittest.mock import patch

from services.report_content import build_grounded_report, parse_recommendations, report_signature
from services.ai_insights import generate_competitor_insights


class ReportContentTests(unittest.TestCase):
    def setUp(self):
        self.business = {"name": "DMart", "location": "Velachery, Chennai", "source": "OpenStreetMap"}
        self.rows = [{"Name": "Market A", "Category": "Supermarket", "Distance (km)": .1, "Classification": "Direct", "Confidence": "High", "AI Reason": "A verified discount advantage", "Discovery source": "OpenStreetMap nearby search (limited best matches)"}]

    def test_factual_report_does_not_reuse_unsupported_classification_reason(self):
        report = build_grounded_report(self.business, self.rows)
        self.assertIn("1 classified as direct", report)
        self.assertIn("0.10 km", report)
        self.assertIn("list is not exhaustive", report)
        self.assertIn("C1 - Market A", report)
        self.assertNotIn("A verified discount advantage", report)
        self.assertIn("Evidence score: Unavailable", report)

    def test_area_location_and_zero_observed_values_are_preserved(self):
        self.business["resolution_status"] = "area_center"
        self.business["User-supplied evidence (not independently verified)"] = {"Active Ads": 0, "Source": "User audit", "Observed On": "2026-10-25"}
        report = build_grounded_report(self.business, self.rows)
        self.assertIn("approximate centre, not the store", report)
        self.assertIn("Active Ads: 0", report)
        self.assertIn("User audit", report)
        self.assertIn("2026-10-25", report)

    def test_recommendations_require_known_evidence_references(self):
        actions = [{"action": "Verify category", "why": "Collect evidence", "evidence_ids": ["B1", "C1"]}] * 5
        self.assertEqual(len(parse_recommendations(json.dumps({"recommendations": actions}), 1)), 5)
        actions[0] = dict(actions[0], evidence_ids=["C99"])
        with self.assertRaises(ValueError):
            parse_recommendations(json.dumps({"recommendations": actions}), 1)

    def test_unstructured_ai_claims_are_discarded(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch("services.ai_insights.genai.Client"), patch("services.ai_insights.generate_with_auto_fallback", return_value="DMart has unmatched discount prices and guaranteed high foot traffic."):
            report = generate_competitor_insights(self.business, self.rows)
        self.assertNotIn("unmatched discount prices", report)
        self.assertIn("standard validation steps", report)

    def test_valid_ai_output_is_labelled_as_unverified_suggestions(self):
        actions = [{"action": "Check prices using a comparable basket", "why": "Test whether any price advantage exists", "evidence_ids": ["B1", "C1"]}] * 5
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch("services.ai_insights.genai.Client"), patch("services.ai_insights.generate_with_auto_fallback", return_value=json.dumps({"recommendations": actions})):
            report = generate_competitor_insights(self.business, self.rows)
        self.assertIn("unverified proposals, not findings", report)
        self.assertIn("References: B1, C1", report)

    def test_signature_changes_with_report_schema(self):
        legacy = json.dumps({"business": self.business, "competitors": self.rows}, sort_keys=True)
        self.assertNotEqual(report_signature(self.business, self.rows), legacy)

    def test_website_observations_include_source_and_time_without_inventing_metrics(self):
        self.business["Website analysis"] = {"Status": "Available", "Source URL": "https://example.org/", "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00", "Page title": "Public shop page", "Description": "Page description", "On-page keyword candidates": ["grocery", "delivery"]}
        report = build_grounded_report(self.business, self.rows)
        self.assertIn("https://example.org/", report)
        self.assertIn("2026-10-25T12:00:00+00:00", report)
        self.assertIn("Public shop page", report)
        self.assertIn("On-page keyword candidates: grocery; delivery", report)
        self.assertIn("Evidence score: Unavailable", report)

    def test_report_uses_only_captured_terms_for_possible_gaps(self):
        page = {"Status": "Available", "Source URL": "https://example.org", "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00"}
        self.business["Website analysis"] = {**page, "On-page keyword candidates": ["fresh"]}
        self.rows[0]["Website analysis"] = {**page, "On-page keyword candidates": ["organic"]}
        report = build_grounded_report(self.business, self.rows)
        self.assertIn("Term to review: organic", report)
        self.assertIn("not a verified SEO opportunity", report)
        self.assertIn("Search volume and Google rankings are unavailable", report)
        self.assertIn("rule-based estimates", report)
