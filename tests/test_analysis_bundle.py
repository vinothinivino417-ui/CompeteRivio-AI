import copy
import csv
import hashlib
import io
import json
import unittest
import zipfile

from history_fixtures import make_state, sign_state
from services.analysis_history import current_snapshot, archive_current_analysis
from services.analysis_bundle import create_analysis_bundle
from services.competitor_evidence import evidence_scope
from services.history_backup import restore_history


class AnalysisBundleTests(unittest.TestCase):
    def setUp(self):
        self.state = make_state()
        scope = evidence_scope(self.state["business_profile"])
        self.state["competitor_evidence"] = {scope: {"business": {"Active Ads": 0, "Source": "Audit", "Observed On": "2026-10-25"}}}
        sign_state(self.state)
        self.snapshot = current_snapshot(self.state)
        self.pdf = b"%PDF-test-existing-report-bytes"

    def bundle(self, snapshot=None, record=None):
        return zipfile.ZipFile(io.BytesIO(create_analysis_bundle(snapshot or self.snapshot, self.pdf, record)))

    def rows(self, archive, name):
        return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))

    def test_manifest_matches_exact_files_and_snapshot_is_unchanged(self):
        before = copy.deepcopy(self.snapshot)
        with self.bundle() as archive:
            self.assertEqual(len(archive.namelist()), 9)
            self.assertTrue(all("/" not in name and "\\" not in name for name in archive.namelist()))
            self.assertEqual(archive.read("report.pdf"), self.pdf)
            self.assertEqual(archive.read("report.md").decode(), self.snapshot["report"])
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(set(manifest["files"]), set(archive.namelist()) - {"manifest.json"})
            for name, metadata in manifest["files"].items():
                self.assertEqual(metadata["sha256"], hashlib.sha256(archive.read(name)).hexdigest())
                self.assertEqual(metadata["bytes"], len(archive.read(name)))
        self.assertEqual(before, self.snapshot)

    def test_missing_values_and_observed_zero_are_distinct(self):
        with self.bundle() as archive:
            rows = self.rows(archive, "evidence_and_scores.csv")
            self.assertEqual(rows[0]["Active Ads"], "0")
            self.assertEqual(rows[1]["Active Ads"], "")
            self.assertEqual(rows[0]["Source"], "Audit")
            self.assertEqual(rows[0]["Observed On"], "2026-10-25")
            self.assertEqual(self.rows(archive, "captured_keyword_observations.csv"), [])

    def test_restore_from_extracted_backup_and_preserve_saved_date(self):
        record = archive_current_analysis(self.state)
        with self.bundle(record=record) as archive:
            restored = {}
            restore_history(restored, archive.read("history_backup.json"))
            saved = restored["analysis_history"][0]
            self.assertEqual(saved["snapshot"], record["snapshot"])
            self.assertEqual(saved["created_at"], record["created_at"])

    def test_formula_text_is_escaped_in_csv_and_original_preserved_in_json(self):
        self.snapshot["competitors"][0]["Name"] = "=1+1"
        with self.bundle() as archive:
            self.assertEqual(self.rows(archive, "competitors.csv")[0]["Name"], "'=1+1")
            self.assertEqual(json.loads(archive.read("analysis_snapshot.json"))["competitors"][0]["Name"], "=1+1")

    def test_keyword_sources_are_included_without_network_access(self):
        self.snapshot["business"]["Website analysis"] = {"Status": "Available", "Source URL": "https://example.org/", "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00", "On-page keyword candidates": ["grocery"]}
        with self.bundle() as archive:
            row = self.rows(archive, "captured_keyword_observations.csv")[0]
            self.assertEqual(row["Term"], "grocery")
            self.assertEqual(row["Evidence ID"], "B1")
            self.assertEqual(row["Source URL"], "https://example.org/")

    def test_invalid_snapshot_or_pdf_is_rejected_and_root_state_is_excluded(self):
        with self.assertRaises(ValueError):
            create_analysis_bundle({}, self.pdf)
        with self.assertRaises(ValueError):
            create_analysis_bundle(self.snapshot, b"invalid")
        self.snapshot["GEMINI_API_KEY"] = "root-secret-not-to-export"
        with self.bundle() as archive:
            self.assertNotIn(b"root-secret-not-to-export", archive.read("analysis_snapshot.json"))
            self.assertNotIn(b"root-secret-not-to-export", archive.read("history_backup.json"))
