from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class EvidenceReviewUITests(unittest.TestCase):
    def test_review_warning_and_unavailable_dates_render(self):
        app = AppTest.from_file(str(Path(__file__).with_name("evidence_review_app.py"))).run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.warning), 1)
        self.assertIn("1 record(s)", app.warning[0].value)
        frame = app.dataframe[0].value
        self.assertEqual(frame.iloc[0]["Review status"], "Review due")
        self.assertEqual(frame.iloc[1]["Age (days)"], "Unavailable")
        self.assertTrue(any("not a verified expiry date" in item.value for item in app.caption))
