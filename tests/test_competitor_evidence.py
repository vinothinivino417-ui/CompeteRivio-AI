from datetime import date
import unittest

from services.competitor_evidence import (
    validate_evidence, calculate_scores, evidence_scope, enrich_report_inputs,
)


class CompetitorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.targets = [{"Target ID": "business", "Name": "Apollo"}, {"Target ID": "node:2", "Name": "Hospital B"}]
        self.ids = {row["Target ID"] for row in self.targets}

    def record(self, target_id, **values):
        return {"Target ID": target_id, "Source": "Manual observation", "Observed On": date.today().isoformat(), **values}

    def test_zero_is_evidence_and_blank_is_missing(self):
        saved = validate_evidence([self.record("business", **{"Active Ads": "0", "Rating": ""})], self.ids)
        self.assertEqual(saved["business"]["Active Ads"], 0)
        self.assertNotIn("Rating", saved["business"])

    def test_rejects_invalid_data_and_missing_provenance(self):
        for value in [-1, "nan", "inf", "text", 1.5]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_evidence([self.record("business", **{"Review Count": value})], self.ids)
        for row in [self.record("business", Rating=6), self.record("business", Rating=4, Source=""),
                    self.record("business", Rating=4, **{"Observed On": "bad"}),
                    self.record("business", Rating=4, **{"Observed On": "2999-01-01"}),
                    self.record("unknown", Rating=4)]:
            with self.assertRaises(ValueError):
                validate_evidence([row], self.ids)
        with self.assertRaises(ValueError):
            validate_evidence([self.record("business"), self.record("business")], self.ids)

    def test_same_categories_and_weights_for_every_target(self):
        evidence = validate_evidence([
            self.record("business", Rating=4, **{"Review Count": 100, "Active Ads": 0}),
            self.record("node:2", Rating=5, **{"Review Count": 200, "Active Ads": 5}),
        ], self.ids)
        scores = calculate_scores(self.targets, evidence)
        self.assertEqual([row["Evidence score"] for row in scores], [0, 100])
        self.assertEqual(scores[0]["PRD weight coverage (%)"], 35)
        self.assertEqual(set(scores[0]["Breakdown"]), {"Reputation", "Paid activity"})

    def test_missing_metric_excludes_entire_category_for_everyone(self):
        evidence = {"business": {"Rating": 5, "Review Count": 100, "Active Ads": 0}, "node:2": {"Rating": 4, "Active Ads": 0}}
        scores = calculate_scores(self.targets, evidence)
        self.assertEqual([row["Evidence score"] for row in scores], [50, 50])
        self.assertEqual(scores[0]["PRD weight coverage (%)"], 15)
        self.assertNotIn("Reputation", scores[0]["Breakdown"])

    def test_no_evidence_or_single_business_has_no_score(self):
        self.assertTrue(all(row["Evidence score"] is None for row in calculate_scores(self.targets, {})))
        self.assertIsNone(calculate_scores(self.targets[:1], {"business": {"Active Ads": 3}})[0]["Evidence score"])

    def test_report_enrichment_does_not_mix_businesses(self):
        business = {"name": "Apollo", "osm_id": 1}
        approved = [{"Name": "Hospital B", "OSM ID": "2", "OSM Type": "node"}]
        saved = {evidence_scope(business): {"business": {"Active Ads": 0}, "node:2": {"Active Ads": 5}}}
        enriched_business, enriched = enrich_report_inputs(business, approved, saved)
        self.assertEqual(enriched[0]["Partial evidence scoring"]["Evidence score"], 100)
        self.assertEqual(enriched_business["Partial evidence scoring"]["Evidence score"], 0)
        _, other = enrich_report_inputs({"name": "Another business"}, approved, saved)
        self.assertEqual(other[0]["User-supplied evidence (not independently verified)"], {})
        self.assertNotIn("Partial evidence scoring", approved[0])


if __name__ == "__main__":
    unittest.main()
