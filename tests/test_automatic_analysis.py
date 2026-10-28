import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from streamlit.testing.v1 import AppTest

from services.automatic_analysis import run_automatic_analysis, generate_saved_report, canonicalize_search, check_saved_websites


class AutomaticAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.search = patch("services.automatic_analysis.search_business").start()
        self.fetch = patch("services.automatic_analysis.fetch_nearby_businesses").start()
        self.classify = patch("services.automatic_analysis.classify_competitors_with_gemini").start()
        self.report = patch("services.automatic_analysis.generate_competitor_insights").start()
        self.area = patch("services.automatic_analysis.find_area", return_value=[]).start()
        self.addCleanup(patch.stopall)
        self.search.return_value = [{"name": "Apollo Hospital", "display_name": "Test city", "lat": "13", "lon": "80", "osm_id": 1, "osm_type": "node"}]
        self.fetch.return_value = [
            {"id": i, "type": "node", "lat": 13 + i / 10000, "lon": 80, "tags": {"name": f"Hospital {i}"}}
            for i in range(2, 22)
        ]
        self.classify.side_effect = lambda business, candidates: [
            {**row, "Classification": "Irrelevant" if i == 0 else "Direct"} for i, row in enumerate(candidates)
        ]
        self.report.return_value = "A report based on supplied evidence."

    def run_analysis(self, state=None):
        state = {} if state is None else state
        run_automatic_analysis(state, "Apollo", "Test city", "Hospital", 3)
        return state

    def test_one_action_completes_full_pipeline(self):
        state = self.run_analysis()
        self.search.assert_called_once_with("Apollo", "Test city", strict_location=True)
        self.assertEqual(len(self.classify.call_args.args[1]), 15)
        self.assertEqual(len(state["discovered_competitors"]), 20)
        self.assertEqual(len(state["approved_competitors"]), 14)
        self.assertEqual(state["competitor_selection_mode"], "automatic")
        self.assertEqual(state["ai_insights_report"], self.report.return_value)
        self.assertEqual(len(state["analysis_history"]), 1)
        self.assertEqual(state["analysis_history"][0]["snapshot"]["report"], self.report.return_value)
        self.assertEqual(state["automatic_warnings"], [])
        self.assertIn("Selection", self.report.call_args.args[1][0])

    def test_failed_lookup_preserves_previous_workspace(self):
        self.search.return_value = []
        state = {"business_profile": {"name": "Old"}, "ai_insights_report": "Old report"}
        before = dict(state)
        with self.assertRaises(ValueError):
            self.run_analysis(state)
        self.assertEqual(state, before)
        self.fetch.assert_not_called()

    def test_discovery_failure_preserves_previous_workspace(self):
        self.fetch.side_effect = RuntimeError("Map server unavailable")
        state = {"business_profile": {"name": "Old"}}
        with self.assertRaises(RuntimeError):
            self.run_analysis(state)
        self.assertEqual(state, {"business_profile": {"name": "Old"}})

    def test_missing_store_uses_area_without_pretending_store_is_verified(self):
        self.search.return_value = []
        self.area.return_value = [{"name": "Velachery", "display_name": "Velachery, Chennai", "lat": "13", "lon": "80", "osm_id": 999, "osm_type": "relation", "extratags": {"website": "https://example.org/city"}}]
        state = {}
        run_automatic_analysis(state, "D Mart", "Velachery, Chennai", "Supermarket", 3)
        self.assertEqual(state["business_profile"]["name"], "DMart")
        self.assertIsNone(state["business_profile"]["osm_id"])
        self.assertEqual(state["business_profile"]["resolution_status"], "area_center")
        self.assertEqual(state["business_profile"]["website"], "")
        self.assertIn("area-based analysis", state["automatic_warnings"][0])
        self.assertEqual(self.report.call_args.args[0]["resolution_status"], "area_center")
        self.assertTrue(all(row["Distance reference"] == "Approximate area centre" for row in state["approved_competitors"]))

    def test_store_name_spacing_is_matched_in_area_data_and_self_is_excluded(self):
        self.search.return_value = []
        self.area.return_value = [{"name": "Velachery", "lat": "13", "lon": "80"}]
        store = {"id": 50, "type": "node", "lat": 13.001, "lon": 80, "tags": {"name": "DMart"}}
        self.fetch.return_value = self.fetch.return_value + [store]
        state = {}
        run_automatic_analysis(state, "D Mart", "Velachery, Chennai", "Supermarket", 3)
        self.assertEqual(state["business_profile"]["osm_id"], 50)
        self.assertEqual(state["business_profile"]["resolution_status"], "business_listing")
        self.assertEqual(self.fetch.call_count, 2)
        self.assertTrue(all(row["OSM ID"] != "50" for row in state["discovered_competitors"]))
        self.assertEqual(state["automatic_warnings"], [])

    def test_classifier_failure_keeps_unclassified_candidates(self):
        self.classify.side_effect = RuntimeError("Free quota exceeded")
        state = self.run_analysis()
        self.assertEqual(len(state["approved_competitors"]), 15)
        self.assertTrue(all(row["Classification"] == "Not classified" for row in state["approved_competitors"]))
        self.assertTrue(state["automatic_warnings"])
        self.assertIn("ai_insights_report", state)

    def test_irrelevant_candidates_are_labelled_unverified(self):
        self.classify.side_effect = lambda business, candidates: [{**row, "Classification": "Irrelevant"} for row in candidates]
        state = self.run_analysis()
        self.assertTrue(all(row["Classification"] == "Irrelevant" for row in state["approved_competitors"]))
        self.assertIn("relevance is unverified", state["automatic_warnings"][0])

    def test_report_retry_does_not_repeat_discovery_or_classification(self):
        self.report.side_effect = RuntimeError("Quota exceeded")
        state = self.run_analysis()
        self.assertIn("Report mode:", state["ai_insights_report"])
        self.assertIn("standard validation steps", state["ai_insights_report"])
        self.assertIn("AI recommendations were unavailable", state["report_generation_note"])
        self.assertTrue(state["approved_competitors"])
        self.report.side_effect = None
        self.report.return_value = "Recovered report"
        generate_saved_report(state)
        self.assertEqual(state["ai_insights_report"], "Recovered report")
        self.assertEqual(state["report_generation_note"], "")
        self.assertEqual(self.search.call_count, 1)
        self.assertEqual(self.classify.call_count, 1)

    def test_both_ai_services_unavailable_still_save_a_factual_report(self):
        self.classify.side_effect = RuntimeError("503 UNAVAILABLE: high demand")
        self.report.side_effect = RuntimeError("503 UNAVAILABLE: high demand")
        state = self.run_analysis()
        self.assertTrue(all(row["Classification"] == "Not classified" for row in state["approved_competitors"]))
        self.assertIn("0 classified as direct", state["ai_insights_report"])
        self.assertIn("AI recommendations were unavailable", state["ai_insights_report"])
        self.assertEqual(state["analysis_history"][0]["snapshot"]["report"], state["ai_insights_report"])
        self.assertFalse(any("Details:" in warning for warning in state["automatic_warnings"]))

    def test_no_ai_report_uses_saved_data_without_external_calls(self):
        state = self.run_analysis()
        self.report.reset_mock()
        self.classify.reset_mock()
        self.search.reset_mock()
        state["automatic_warnings"] = ["Your discovered businesses are saved, but the AI report could not finish.", "Limited discovery"]
        generate_saved_report(state, use_ai=False)
        self.report.assert_not_called()
        self.classify.assert_not_called()
        self.search.assert_not_called()
        self.assertIn("No AI request was made", state["ai_insights_report"])
        self.assertEqual(state["automatic_warnings"], ["Limited discovery"])

    def test_empty_ai_output_uses_factual_fallback(self):
        self.report.return_value = ""
        state = self.run_analysis()
        self.assertIn("Report mode:", state["ai_insights_report"])

    def test_factual_report_button_recovers_a_saved_failed_run(self):
        state = self.run_analysis()
        state.pop("ai_insights_report")
        state.pop("ai_insights_input")
        self.report.reset_mock()
        app = AppTest.from_file(str(Path(__file__).with_name("automatic_analysis_app.py")), default_timeout=30)
        for key, value in state.items():
            app.session_state[key] = value
        app.run()
        app.button(key="auto_factual_report").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertIn("No AI request was made", app.session_state["ai_insights_report"])
        self.report.assert_not_called()
        self.assertEqual(self.search.call_count, 1)

    def test_report_for_wrong_business_is_blocked(self):
        state = self.run_analysis()
        state["business_profile"]["osm_id"] = 99
        with self.assertRaises(ValueError):
            generate_saved_report(state)

    def test_invalid_inputs_do_not_call_services(self):
        with self.assertRaises(ValueError):
            run_automatic_analysis({}, "", "Test city", "Hospital", 3)
        self.search.assert_not_called()

    def test_website_checks_can_be_disabled(self):
        with patch("services.automatic_analysis.enrich_websites") as websites:
            run_automatic_analysis({}, "Apollo", "Test city", "Hospital", 3, include_websites=False)
        websites.assert_not_called()

    def test_refreshing_websites_does_not_repeat_ai_or_discovery(self):
        state = self.run_analysis()
        def enriched(business, competitors, progress):
            return {**business, "Website analysis": {"Status": "Available"}}, [{**row, "Website analysis": {"Status": "Available"}} for row in competitors]
        with patch("services.automatic_analysis.enrich_websites", side_effect=enriched):
            check_saved_websites(state)
        self.assertEqual(self.search.call_count, 1)
        self.assertEqual(self.classify.call_count, 1)
        self.assertEqual(self.report.call_count, 1)
        self.assertNotIn("ai_insights_report", state)
        self.assertEqual(state["approved_competitors"][0]["Website analysis"]["Status"], "Available")

    def test_reported_search_spelling_is_corrected_and_shown_to_lookup(self):
        self.assertEqual(canonicalize_search("Brandmonk Academy", "valasaravakkam, chennai, tamildnadu"), ("Brandmonk Academy", "valasaravakkam, chennai, Tamil Nadu"))
        self.assertEqual(canonicalize_search('D Mart', 'velacherry, chennai, tamilnadu'), ('DMart', 'Velachery, chennai, Tamil Nadu'))
        self.assertEqual(canonicalize_search('Local Store', 'Velacherry, Another City'), ('Local Store', 'Velacherry, Another City'))
        run_automatic_analysis({}, 'D Mart', 'velacherry, chennai, tamilnadu', 'Supermarket', 3)
        self.search.assert_called_once_with('DMart', 'Velachery, chennai, Tamil Nadu', strict_location=True)

    def test_form_runs_pipeline_and_rerender_does_not_repeat_api_calls(self):
        app = AppTest.from_file(str(Path(__file__).with_name("automatic_analysis_app.py")), default_timeout=30).run()
        self.assertFalse(app.exception)
        app.text_input[0].set_value("Apollo")
        app.text_input[1].set_value("Test city")
        next(button for button in app.button if button.label == "Find business profile").click().run()
        self.fetch.assert_not_called()
        self.classify.assert_not_called()
        self.report.assert_not_called()
        app.button(key="auto_confirm_profile").click().run()
        self.report.assert_not_called()
        app.button(key="auto_approve_report").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["ai_insights_report"], self.report.return_value)
        self.assertEqual(app.session_state["main_navigation"], "Overview")
        self.assertEqual(len(app.session_state["approved_competitors"]), 14)
        app.run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(self.search.call_count, 1)
        self.assertEqual(self.classify.call_count, 1)
        self.assertEqual(self.report.call_count, 1)

    def test_user_selected_profile_is_used_for_discovery(self):
        self.search.return_value.append({"name": "Second branch", "display_name": "Other street", "lat": "13.002", "lon": "80", "osm_id": 99, "osm_type": "node"})
        app = AppTest.from_file(str(Path(__file__).with_name("automatic_analysis_app.py")), default_timeout=30).run()
        app.text_input[0].set_value("Apollo")
        app.text_input[1].set_value("Test city")
        next(b for b in app.button if b.label == "Find business profile").click().run()
        selector = next(s for s in app.selectbox if s.label == "Matching profile")
        selector.set_value(1).run()
        self.fetch.assert_not_called()
        app.button(key="auto_confirm_profile").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["business_profile"]["name"], "Second branch")
        self.assertEqual(self.fetch.call_args.args[0], 13.002)
        self.assertEqual(self.search.call_count, 1)
        self.report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
