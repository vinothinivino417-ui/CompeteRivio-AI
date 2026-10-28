import copy
from datetime import date, timedelta
import unittest

from services.evidence_review import build_evidence_review


class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 25)

    def business(self, observed):
        return {"name": "Store", "User-supplied evidence (not independently verified)": {"Active Ads": 0, "Observed On": observed, "Source": "Manual audit"}}

    def test_zero_is_measurement_and_ninety_day_boundary_is_inclusive(self):
        for age, expected in [(0, "Within review window"), (89, "Within review window"), (90, "Review due"), (120, "Review due")]:
            business = self.business((self.today - timedelta(days=age)).isoformat())
            before = copy.deepcopy(business)
            row = build_evidence_review(business, [], self.today)["Rows"][0]
            self.assertEqual(row["Review status"], expected)
            self.assertEqual(row["Age (days)"], age)
            self.assertEqual(row["Available measurements"], "Active Ads")
            self.assertEqual(business, before)

    def test_missing_invalid_and_future_dates_are_not_recent(self):
        for observed, expected in [(None, "Date missing"), ("bad", "Date invalid"), ("2026-10-26", "Future date — check")]:
            row = build_evidence_review(self.business(observed), [], self.today)["Rows"][0]
            self.assertEqual(row["Review status"], expected)
            self.assertIsNone(row["Age (days)"])

    def test_unavailable_measurements_are_separate_from_missing_dates(self):
        rows = build_evidence_review({"name": "Own"}, [{"Name": "Other"}], self.today)["Rows"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["Review status"], "No measurements")
        self.assertEqual(rows[1]["Review status"], "No usable website capture")
        self.assertEqual(rows[2]["Reference"], "C1")

    def test_website_dates_are_aware_and_compared_in_india_time(self):
        business = {"name": "Own", "Website analysis": {"Status": "Available", "Source URL": "https://example.org", "Retrieved at (UTC)": "2026-10-24T20:00:00+00:00"}}
        row = build_evidence_review(business, [], self.today)["Rows"][1]
        self.assertEqual(row["Age (days)"], 0)
        business["Website analysis"]["Retrieved at (UTC)"] = "2026-10-25T10:00:00"
        self.assertEqual(build_evidence_review(business, [], self.today)["Rows"][1]["Review status"], "Date invalid")
        business["Website analysis"]["Status"] = "Unavailable"
        self.assertEqual(build_evidence_review(business, [], self.today)["Rows"][1]["Review status"], "No usable website capture")
