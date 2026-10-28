import json
import unittest

from services.lighthouse_audit import parse_lighthouse_report


class LighthouseAuditTests(unittest.TestCase):
    def report(self):
        return {"lighthouseVersion": "12.0", "finalUrl": "https://example.com/",
                "fetchTime": "2025-01-01T10:00:00Z", "configSettings": {"formFactor": "mobile"},
                "categories": {"performance": {"score": 0}, "seo": {"score": 0.95}}}

    def test_zero_and_unavailable_are_distinct(self):
        audit = parse_lighthouse_report(json.dumps(self.report()))
        self.assertEqual(audit["Performance"], 0)
        self.assertEqual(audit["SEO"], 95)
        self.assertIsNone(audit["Accessibility"])

    def test_pagespeed_wrapper(self):
        self.assertEqual(parse_lighthouse_report(json.dumps({"lighthouseResult": self.report()}))["Device"], "mobile")

    def test_invalid_scores_rejected(self):
        for value in (True, -0.1, 1.5, "0.5", float("nan")):
            report = self.report()
            report["categories"]["seo"]["score"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_lighthouse_report(json.dumps(report))

    def test_invalid_documents_rejected(self):
        for value in ("[]", "{}", "not json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_lighthouse_report(value)

    def test_future_dates_rejected(self):
        report = self.report()
        report["fetchTime"] = "2999-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            parse_lighthouse_report(json.dumps(report))
