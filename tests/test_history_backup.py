import copy
import json
import unittest

from history_fixtures import make_state
from services.analysis_history import archive_current_analysis, MAX_HISTORY
from services.history_backup import prepare_history_restore, restore_history, MAX_BACKUP_BYTES


class HistoryBackupTests(unittest.TestCase):
    def setUp(self):
        state = make_state()
        self.record = archive_current_analysis(state)

    def payload(self, records=None):
        return json.dumps({"schema_version": 1, "analyses": records if records is not None else [self.record]}).encode()

    def test_round_trip_and_repeat_restore_do_not_replace_active_analysis(self):
        state = make_state()
        before = copy.deepcopy(state)
        preview = prepare_history_restore(state, self.payload())
        self.assertEqual(preview["added"], 1)
        self.assertEqual(state, before)
        self.assertEqual(restore_history(state, self.payload()), {"added": 1, "duplicates": 0})
        saved = state["analysis_history"][0]
        self.assertEqual(saved["snapshot"], self.record["snapshot"])
        self.assertEqual(saved["created_at"], self.record["created_at"])
        for key, value in before.items():
            self.assertEqual(state[key], value)
        self.assertEqual(restore_history(state, self.payload()), {"added": 0, "duplicates": 1})

    def test_duplicate_records_and_forged_identifiers_are_handled(self):
        state = {"analysis_history": [copy.deepcopy(self.record)]}
        other = copy.deepcopy(self.record)
        other["snapshot"]["report"] = "# Another report"
        other["fingerprint"] = self.record["fingerprint"]
        result = restore_history(state, self.payload([self.record, other, other]))
        self.assertEqual(result, {"added": 1, "duplicates": 2})
        self.assertEqual(len({row["id"] for row in state["analysis_history"]}), 2)

    def test_invalid_record_prevents_partial_import(self):
        bad = copy.deepcopy(self.record)
        bad["snapshot"]["competitors"] = ["invalid"]
        state = {"business_profile": {"name": "Current"}}
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            restore_history(state, self.payload([self.record, bad]))
        self.assertEqual(state, before)

    def test_capacity_never_deletes_or_partially_imports(self):
        state = {"analysis_history": [{**copy.deepcopy(self.record), "id": str(index)} for index in range(MAX_HISTORY)]}
        other = copy.deepcopy(self.record)
        other["snapshot"]["report"] = "# New report"
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            restore_history(state, self.payload([other]))
        self.assertEqual(state, before)
        self.assertEqual(restore_history(state, self.payload())["added"], 0)

    def test_invalid_formats_dates_numbers_and_size(self):
        for payload in [b"not json", b"[]", b'{"schema_version":2,"analyses":[]}', b'\xff', b" " * (MAX_BACKUP_BYTES + 1)]:
            with self.subTest(payload=payload[:30]), self.assertRaises(ValueError):
                prepare_history_restore({}, payload)
        for field, value in [("created_at", "bad"), ("created_at", "2026-01-01"), ("schema_version", True)]:
            invalid = copy.deepcopy(self.record)
            invalid[field] = value
            with self.assertRaises(ValueError):
                prepare_history_restore({}, self.payload([invalid]))
        invalid = copy.deepcopy(self.record)
        invalid["snapshot"]["radius_km"] = float("nan")
        with self.assertRaises(ValueError):
            prepare_history_restore({}, self.payload([invalid]))

    def test_unknown_root_fields_are_not_restored(self):
        record = {**self.record, "api_key": "ignored"}
        state = {}
        restore_history(state, self.payload([record]))
        self.assertNotIn("api_key", state["analysis_history"][0])
