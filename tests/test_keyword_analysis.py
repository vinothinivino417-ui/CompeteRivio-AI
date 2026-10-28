import unittest

from services.keyword_analysis import captured_terms, build_keyword_analysis


def audit(terms, status="Available", url="https://example.org/"):
    return {"Status": status, "Source URL": url, "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00", "On-page keyword candidates": terms}


class KeywordAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.business = {"name": "DMart", "Website analysis": audit(["Fresh", "Delivery"], url="https://business.example/")}
        self.competitors = [{"Name": "Market A", "Website analysis": audit(["fresh", "organic"])}]

    def test_normalization_deduplicates_observed_and_declared_terms(self):
        page = audit([" Fresh ", "Ｆｒｅｓｈ", "Delivery"])
        page["Declared meta keywords"] = ["fresh", "organic grocery", "x" * 101]
        self.assertEqual(captured_terms(page), {"fresh", "delivery", "organic grocery"})

    def test_gap_is_only_absent_from_captured_sample(self):
        analysis = build_keyword_analysis(self.business, self.competitors)
        self.assertEqual([row["Term"] for row in analysis["Potential gaps"]], ["organic"])
        self.assertEqual(analysis["Potential gaps"][0]["Evidence references"], "C1")
        shared = next(row for row in analysis["Rows"] if row["Term"] == "fresh")
        self.assertEqual(shared["Review"], "Shared captured term")
        self.assertEqual(shared["Evidence references"], "B1, C1")

    def test_missing_own_page_never_creates_content_gaps(self):
        self.business["Website analysis"] = {"Status": "Blocked"}
        analysis = build_keyword_analysis(self.business, self.competitors)
        self.assertEqual(analysis["Potential gaps"], [])
        self.assertTrue(all(row["Your captured terms"] == "Unavailable" for row in analysis["Rows"]))

    def test_empty_page_is_unknown_not_zero(self):
        analysis = build_keyword_analysis(self.business, [{"Name": "Empty", "Website analysis": audit([])}])
        self.assertFalse(analysis["Entities"][1]["Usable"])
        self.assertEqual(analysis["Entities"][1]["Terms"], set())

    def test_blocked_page_and_missing_provenance_are_excluded(self):
        self.assertEqual(captured_terms(audit(["secret"], status="Blocked")), set())
        self.assertEqual(captured_terms({"Status": "Available", "On-page keyword candidates": ["untraceable"]}), set())

    def test_observations_preserve_source_and_timestamp(self):
        analysis = build_keyword_analysis(self.business, self.competitors)
        source = next(row for row in analysis["Observations"] if row["Term"] == "organic")
        self.assertEqual(source["Source URL"], "https://example.org/")
        self.assertEqual(source["Retrieved at (UTC)"], "2026-10-25T12:00:00+00:00")
        self.assertEqual(source["Evidence ID"], "C1")
        self.assertNotIn("Search Volume", analysis["Rows"][0])
        self.assertNotIn("Ranking", analysis["Rows"][0])

    def test_duplicate_business_names_have_distinct_labels(self):
        analysis = build_keyword_analysis(self.business, self.competitors * 2)
        labels = [entity["Label"] for entity in analysis["Entities"]]
        self.assertEqual(len(set(labels)), len(labels))

    def test_no_website_data_has_no_terms(self):
        analysis = build_keyword_analysis({"name": "DMart"}, [{"Name": "Market"}])
        self.assertEqual(analysis["Terms"], [])
        self.assertEqual(analysis["Observations"], [])
