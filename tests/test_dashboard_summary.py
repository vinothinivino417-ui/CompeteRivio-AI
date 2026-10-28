import unittest
from services.dashboard_summary import summarize_selection


class DashboardSummaryTests(unittest.TestCase):
    def test_unavailable_classification_and_invalid_distances_are_not_zero(self):
        rows = [{"Classification":"Not classified", "Distance (km)": value} for value in [None, "bad", float("inf"), -1, True]]
        summary = summarize_selection(rows)
        self.assertIsNone(summary["direct"])
        self.assertIsNone(summary["indirect"])
        self.assertIsNone(summary["nearest"])
        self.assertEqual(summary["distance_bands"], [0,0,0])

    def test_selected_counts_and_distance_boundaries(self):
        rows = [{"Classification":classification, "Distance (km)":distance} for classification,distance in [("Direct",0),("Direct",1),("Indirect",2),("Not classified",3)]]
        summary = summarize_selection(rows)
        self.assertEqual((summary["selected"],summary["direct"],summary["indirect"],summary["unclassified"]),(4,2,1,1))
        self.assertEqual(summary["nearest"],0)
        self.assertEqual(summary["distance_bands"],[2,1,1])
