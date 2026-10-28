from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class KeywordPageTests(unittest.TestCase):
    def make_app(self):
        app = AppTest.from_file(str(Path(__file__).with_name("keywords_app.py")), default_timeout=30)
        page = {"Status": "Available", "Source URL": "https://example.org", "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00", "On-page keyword candidates": ["fresh", "delivery"]}
        app.session_state["business_profile"] = {"name": "DMart", "osm_id": 1, "latitude": 13, "longitude": 80, "Website analysis": page}
        app.session_state["business_confirmed"] = True
        app.session_state["competitor_search_key"] = ("1", 13, 80, "Supermarket", 3)
        app.session_state["approved_competitors"] = [
            {"Name": "Market A", "Website analysis": {**page, "Source URL": "https://market.example", "On-page keyword candidates": ["fresh", "organic"]}},
            {"Name": "Market B", "Website analysis": {"Status": "Blocked"}},
        ]
        return app

    def test_real_page_and_filter_work_in_both_themes(self):
        for mode in ("Light", "Dark"):
            app = self.make_app()
            app.session_state["appearance_mode"] = mode
            app.run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.metric[0].value, "3")
            self.assertEqual(app.metric[1].value, "2 / 3")
            app.selectbox(key="keyword_focus").select("Potential content gap").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.dataframe[0].value["Term"].tolist(), ["organic"])

    def test_another_business_does_not_show_stale_terms(self):
        app = self.make_app()
        app.session_state["business_profile"] = {"name": "Another business", "osm_id": 99}
        app.run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.dataframe), 0)

    def test_intent_chart_and_filter(self):
        app = self.make_app().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 3)
        app.selectbox(key="keyword_intent_filter").select("Service").run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(set(app.dataframe[0].value["Term"]), {"delivery", "organic"})
        app.selectbox(key="keyword_intent_filter").select("Informational").run()
        self.assertFalse(app.exception, app.exception)
        self.assertTrue(app.dataframe[0].value.empty)
