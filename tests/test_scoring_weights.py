import unittest

from services.competitor_evidence import DEFAULT_WEIGHTS, WEIGHT_PRESETS, validate_weights, calculate_scores, evidence_scope, weights_for_business
from services.analysis_history import archive_current_analysis, current_snapshot
from history_fixtures import make_state, sign_state


class ScoringWeightTests(unittest.TestCase):
    def setUp(self):
        self.targets = [{"Target ID": "business", "Name": "Own"}, {"Target ID": "node:2", "Name": "Other"}]
        self.evidence = {"business": {"Rating": 5, "Review Count": 200, "Active Ads": 0}, "node:2": {"Rating": 1, "Review Count": 100, "Active Ads": 10}}
        self.weights = {key: 0 for key in DEFAULT_WEIGHTS}
        self.weights.update({"Reputation": 5, "Paid activity": 45})

    def test_presets_and_invalid_weights(self):
        for preset in WEIGHT_PRESETS.values():
            self.assertEqual(sum(validate_weights(preset).values()), 100)
        for invalid in [{key: 0 for key in DEFAULT_WEIGHTS}, {"Reputation": -1}, {"Reputation": float("nan")}, {"Reputation": True}, {"unknown": 5}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_weights(invalid)

    def test_weights_change_scores_and_explain_contributions(self):
        default = calculate_scores(self.targets, self.evidence)
        self.assertEqual(default[0]["Gap vs competitor average"], 14.28)
        scores = calculate_scores(self.targets, self.evidence, self.weights)
        self.assertEqual([row["Evidence score"] for row in scores], [10, 90])
        self.assertEqual(scores[0]["Gap vs competitor average"], -80)
        self.assertEqual(scores[0]["PRD weight coverage (%)"], 35)
        self.assertEqual(scores[0]["Selected weight coverage (%)"], 100)
        for row in scores:
            self.assertAlmostEqual(sum(row["Category contributions"].values()), row["Evidence score"], places=2)
            self.assertAlmostEqual(sum(row["Included weight shares (%)"].values()), 100, places=2)

    def test_unavailable_categories_do_not_produce_scores(self):
        weights = {key: 0 for key in DEFAULT_WEIGHTS}
        weights["Search visibility"] = 100
        scores = calculate_scores(self.targets, self.evidence, weights)
        self.assertTrue(all(row["Evidence score"] is None for row in scores))
        self.assertIsNone(scores[0]["Gap vs competitor average"])

    def test_weights_are_scoped_and_history_preserves_prior_configuration(self):
        state = make_state()
        scope = evidence_scope(state["business_profile"])
        state["scoring_weights"] = {scope: self.weights}
        self.assertEqual(weights_for_business({"name": "Other"}, state["scoring_weights"]), DEFAULT_WEIGHTS)
        sign_state(state)
        record = archive_current_analysis(state)
        state["scoring_weights"][scope] = DEFAULT_WEIGHTS.copy()
        self.assertIsNone(current_snapshot(state))
        self.assertEqual(record["snapshot"]["business"]["Partial evidence scoring"]["Applied weights"], self.weights)
