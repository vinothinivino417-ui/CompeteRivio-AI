from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from services.competitor_evidence import evidence_scope


class ScoringUITests(unittest.TestCase):
    def test_custom_weights_apply_and_invalid_form_keeps_saved_values(self):
        app = AppTest.from_file(str(Path(__file__).with_name("scoring_app.py"))).run()
        app.selectbox[0].select("Custom").run()
        for slider in app.slider:
            slider.set_value(5 if slider.label == "Reputation" else 45 if slider.label == "Paid activity" else 0)
        app.session_state["ai_insights_report"] = "stale report"
        app.button[0].click().run()
        self.assertFalse(app.exception)
        scope = evidence_scope({"name": "Test business"})
        self.assertEqual(app.session_state["scoring_weights"][scope]["Reputation"], 5)
        self.assertEqual(app.selectbox[0].value, "Custom")
        self.assertNotIn("ai_insights_report", app.session_state)
        for slider in app.slider:
            slider.set_value(0)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertEqual(app.session_state["scoring_weights"][scope]["Paid activity"], 45)
