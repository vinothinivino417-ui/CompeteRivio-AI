import copy
import unittest
from services.history_comparison import compare_saved_runs


class HistoryComparisonTests(unittest.TestCase):
    def record(self, rows):
        return {"snapshot": {"business": {"name": "Store", "osm_id": 1}, "competitors": rows, "category": "Retail", "radius_km": 2}}

    def row(self, identifier, name="Market", classification="Direct"):
        return {"OSM ID": identifier, "OSM Type": "node", "Name": name, "Classification": classification}

    def test_identifier_matching_tracks_selection_and_classification_without_mutation(self):
        before = self.record([self.row(1), self.row(2)])
        after = self.record([self.row(1, "Renamed", "Indirect"), self.row(3)])
        original = copy.deepcopy([before, after])
        result = compare_saved_runs(before, after)
        self.assertEqual([result[key] for key in ("added", "removed", "retained")], [1, 1, 1])
        kept = next(row for row in result["competitors"] if row["Identifier"] == "node:1")
        self.assertEqual(kept["Baseline classification"], "Direct")
        self.assertEqual(kept["Comparison classification"], "Indirect")
        self.assertEqual([before, after], original)

    def test_other_business_or_location_is_rejected(self):
        before, after = self.record([]), self.record([])
        after["snapshot"]["business"]["latitude"] = 13
        with self.assertRaises(ValueError):
            compare_saved_runs(before, after)

    def test_duplicate_identifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            compare_saved_runs(self.record([self.row(1), self.row(1)]), self.record([]))

    def test_missing_identifiers_and_empty_selection(self):
        result = compare_saved_runs(self.record([]), self.record([{"Name": "Market", "Latitude": 13}]))
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["competitors"][0]["Comparison classification"], "Unavailable")
