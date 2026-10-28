import copy
import json
import unittest

from services.analysis_history import archive_current_analysis, current_snapshot, history_record, remove_history_record, MAX_HISTORY
from history_fixtures import make_state, sign_state


class AnalysisHistoryTests(unittest.TestCase):
    def test_saved_snapshot_is_independent_of_current_workspace(self):
        state = make_state()
        record = archive_current_analysis(state)
        state["business_profile"]["name"] = "Changed"
        state["approved_competitors"][0]["Name"] = "Changed competitor"
        saved = history_record(state, record["id"])
        self.assertEqual(saved["snapshot"]["business"]["name"], "DMart")
        self.assertEqual(saved["snapshot"]["competitors"][0]["Name"], "Market A")
        saved["snapshot"]["business"]["name"] = "Changed copy"
        self.assertEqual(history_record(state, record["id"])["snapshot"]["business"]["name"], "DMart")

    def test_identical_reports_are_deduplicated(self):
        state = make_state()
        first = archive_current_analysis(state)
        second = archive_current_analysis(state)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(state["analysis_history"]), 1)

    def test_changed_report_creates_another_saved_run(self):
        state = make_state()
        first = archive_current_analysis(state)
        state["ai_insights_report"] = "# Updated report\n\nA different saved analysis."
        second = archive_current_analysis(state)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(state["analysis_history"]), 2)

    def test_stale_data_and_missing_report_are_not_archived(self):
        state = make_state()
        state["business_profile"]["name"] = "Changed business"
        self.assertIsNone(archive_current_analysis(state))
        self.assertNotIn("analysis_history", state)
        state = make_state()
        state.pop("ai_insights_report")
        self.assertIsNone(current_snapshot(state))

    def test_root_secrets_are_not_in_snapshot(self):
        state = make_state()
        state["GEMINI_API_KEY"] = "test-secret-not-to-save"
        record = archive_current_analysis(state)
        self.assertNotIn("test-secret-not-to-save", json.dumps(record))

    def test_full_history_keeps_existing_runs_and_current_report(self):
        state = make_state()
        record = archive_current_analysis(state)
        state["analysis_history"] = [{**copy.deepcopy(record), "id": str(i), "fingerprint": str(i)} for i in range(MAX_HISTORY)]
        before = copy.deepcopy(state["analysis_history"])
        state["ai_insights_report"] = "A new report"
        self.assertIsNone(archive_current_analysis(state))
        self.assertEqual(state["analysis_history"], before)
        self.assertEqual(state["ai_insights_report"], "A new report")
        self.assertIn("not archived", state["analysis_history_warning"])

    def test_delete_only_selected_archive_entry(self):
        state = make_state()
        first = archive_current_analysis(state)
        state["ai_insights_report"] = "Second report"
        second = archive_current_analysis(state)
        self.assertTrue(remove_history_record(state, first["id"]))
        self.assertEqual(state["analysis_history"][0]["id"], second["id"])
        self.assertEqual(state["ai_insights_report"], "Second report")
        self.assertFalse(remove_history_record(state, "unknown-id"))

    def test_history_survives_json_roundtrip(self):
        state = make_state()
        record = archive_current_analysis(state)
        restored = json.loads(json.dumps(state))
        self.assertEqual(history_record(restored, record["id"])["snapshot"]["report"], state["ai_insights_report"])

    def test_invalid_saved_record_is_rejected(self):
        state = {"analysis_history": [{"id": "bad", "schema_version": 99, "snapshot": {}}]}
        with self.assertRaises(ValueError):
            history_record(state, "bad")
