import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.workspace_storage import persistent_workspace, read_workspace, write_workspace


class WorkspaceStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "workspace.json"

    def test_restart_restores_approved_results_and_search_tuple(self):
        state = {
            "business_confirmed": True,
            "business_profile": {"name": "Apollo Hospital"},
            "competitor_search_key": ("1", 13.0, 80.0, "Hospital", 2),
            "approved_competitors": [{"Name": "Hospital A"}],
            "ai_insights_report": "Saved report",
            "competitor_radius": 2,
            "scoring_weights": {"business-scope": {"Reputation": 30}},
            "api_key": "must not be saved",
            "competitor_approval_editor": {"edited_rows": {}},
            "analysis_history": [{"id": "saved-run", "snapshot": {"report": "Historical report"}}],
        }
        errors = []
        with persistent_workspace(state, errors.append, self.path):
            pass
        new_session = {}
        with persistent_workspace(new_session, errors.append, self.path):
            self.assertEqual(new_session["approved_competitors"], state["approved_competitors"])
            self.assertEqual(new_session["competitor_search_key"], state["competitor_search_key"])
            self.assertEqual(new_session["ai_insights_report"], "Saved report")
            self.assertEqual(new_session["analysis_history"], state["analysis_history"])
            self.assertEqual(new_session["scoring_weights"], state["scoring_weights"])
        self.assertEqual(errors, [])
        self.assertNotIn("api_key", self.path.read_text())
        self.assertNotIn("competitor_approval_editor", self.path.read_text())

    def test_clearing_approvals_is_saved(self):
        state = {"approved_competitors": [{"Name": "Hospital A"}]}
        with persistent_workspace(state, self.fail, self.path):
            pass
        with persistent_workspace(state, self.fail, self.path):
            state["approved_competitors"] = []
            state.pop("ai_insights_report", None)
        self.assertEqual(read_workspace(self.path)["approved_competitors"], [])

    def test_rerun_exit_still_saves(self):
        class Rerun(BaseException):
            pass
        state = {}
        with self.assertRaises(Rerun):
            with persistent_workspace(state, self.fail, self.path):
                state["business_confirmed"] = True
                raise Rerun()
        self.assertTrue(read_workspace(self.path)["business_confirmed"])

    def test_corrupt_file_is_preserved(self):
        self.path.write_text("broken json")
        errors = []
        with persistent_workspace({}, errors.append, self.path):
            pass
        self.assertEqual(self.path.read_text(), "broken json")
        self.assertTrue(errors)

    def test_failed_replace_preserves_previous_save(self):
        write_workspace({"approved_competitors": []}, self.path)
        previous = self.path.read_bytes()
        with patch("services.workspace_storage.os.replace", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                write_workspace({"approved_competitors": [{"Name": "New"}]}, self.path)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_hot_reload_keeps_existing_session_and_skips_unselected_widget(self):
        write_workspace({"business_profile": {"name": "Old"}}, self.path)
        state = {"business_profile": {"name": "Current"}, "appearance_mode": None}
        with persistent_workspace(state, self.fail, self.path):
            pass
        saved = read_workspace(self.path)
        self.assertEqual(saved["business_profile"]["name"], "Current")
        self.assertNotIn("appearance_mode", saved)


if __name__ == "__main__":
    unittest.main()
