from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

from services.competitor_evidence import evidence_scope


class MarketingPageTests(unittest.TestCase):
    def make_app(self):
        app = AppTest.from_file(str(Path(__file__).with_name("marketing_app.py")), default_timeout=30)
        business = {"name": "DMart", "osm_id": 1, "latitude": 13, "longitude": 80, "Website analysis": {"Status": "Available", "Source URL": "https://example.org", "Retrieved at (UTC)": "2026-10-25T12:00:00+00:00", "Page title": "Observed title"}}
        app.session_state["business_profile"] = business
        app.session_state["business_confirmed"] = True
        app.session_state["competitor_search_key"] = ("1", 13, 80, "Supermarket", 3)
        app.session_state["approved_competitors"] = [{"Name": "Market A", "OSM ID": "2", "OSM Type": "node"}]
        app.session_state["competitor_evidence"] = {evidence_scope(business): {"business": {"Active Ads": 0, "Source": "User observation", "Observed On": "2000-01-01"}}}
        return app

    def test_sourced_zero_and_missing_counts_render_in_both_themes(self):
        for mode in ("Light", "Dark"):
            app = self.make_app()
            app.session_state["appearance_mode"] = mode
            app.run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.metric[0].value, "1 / 2")
            table = app.dataframe[0].value
            self.assertEqual(table.iloc[0]["Active Ads"], "0")
            self.assertEqual(table.iloc[1]["Active Ads"], "Unavailable")
            app.selectbox(key="marketing_focus").select("Ad-count evidence available").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(len(app.dataframe[0].value), 1)

    def test_no_saved_evidence_does_not_show_demo_ad_counts(self):
        app = self.make_app()
        app.session_state["competitor_evidence"] = {}
        app.run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.metric[0].value, "0 / 2")
        self.assertTrue(any("No ad-count observations" in item.value for item in app.info))

    def test_another_business_cannot_view_stale_marketing_data(self):
        app = self.make_app()
        app.session_state["business_profile"] = {"name": "Other", "osm_id": 99}
        app.run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.dataframe), 0)
