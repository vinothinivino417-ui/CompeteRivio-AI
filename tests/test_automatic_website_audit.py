import unittest
from unittest.mock import patch

from services.automatic_website_audit import enrich_automatic_audits, _pagespeed
from services.report_content import build_grounded_report


class AutomaticWebsiteAuditTests(unittest.TestCase):
    def item(self, url):
        return {"name": "Shop", "Website analysis": {"Status": "Available", "Source URL": url}}

    @patch("services.automatic_website_audit.public_url", side_effect=lambda url: url)
    @patch("services.automatic_website_audit._pagespeed")
    def test_deduplicates_and_limits(self, fetch, validate):
        fetch.return_value = {"Status": "Available", "Performance": 0}
        business, others = enrich_automatic_audits(self.item("https://a.example"), [self.item(url) for url in ("https://a.example", "https://b.example", "https://c.example")])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(business["Lighthouse audit"]["Performance"], 0)
        self.assertEqual(others[-1]["Lighthouse audit"]["Status"], "Skipped")

    @patch("services.automatic_website_audit._pagespeed")
    def test_blocked_and_missing_never_sent(self, fetch):
        business, others = enrich_automatic_audits({}, [{"Website analysis": {"Status": "Blocked", "Source URL": "https://blocked.example", "Reason": "robots.txt blocks access"}}])
        fetch.assert_not_called()
        self.assertEqual(others[0]["Lighthouse audit"]["Reason"], "robots.txt blocks access")

    @patch("services.automatic_website_audit.public_url", side_effect=ValueError("Private address"))
    @patch("services.automatic_website_audit._pagespeed")
    def test_private_address_rejected(self, fetch, validate):
        business, _ = enrich_automatic_audits(self.item("http://localhost"), [])
        fetch.assert_not_called()
        self.assertEqual(business["Lighthouse audit"]["Status"], "Unavailable")

    @patch("services.automatic_website_audit.public_url", side_effect=lambda url: url)
    @patch("services.automatic_website_audit._pagespeed", side_effect=ValueError("Quota unavailable"))
    def test_failure_keeps_discovered_data(self, fetch, validate):
        business, _ = enrich_automatic_audits(self.item("https://example.com"), [])
        self.assertEqual(business["name"], "Shop")
        self.assertEqual(business["Lighthouse audit"]["Reason"], "Quota unavailable")

    def test_report_includes_zero_and_unavailable_scores(self):
        report = build_grounded_report({"name": "Shop", "Lighthouse audit": {"Status": "Available", "Source": "Google PageSpeed Insights", "Performance": 0}}, [])
        self.assertIn("Performance: 0", report)
        self.assertIn("SEO: Unavailable", report)

    @patch("services.automatic_website_audit.requests.Session")
    def test_quota_response(self, session):
        _pagespeed.clear()
        session.return_value.__enter__.return_value.get.return_value.status_code = 429
        with self.assertRaisesRegex(ValueError, "quota"):
            _pagespeed("https://quota.example")
