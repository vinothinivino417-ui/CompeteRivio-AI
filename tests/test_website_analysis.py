import time
import unittest
from unittest.mock import patch

from services.website_analysis import (
    WebsiteError, public_url, extract_page, audit_website, enrich_websites,
    _audit_public, _robots_policy, MAX_SITES,
)


HTML = '''<html><head><title>Example Services</title><meta name="description" content="Our public service page."><meta name="keywords" content="groceries, retail"></head>
<body><h1>Grocery delivery</h1><h2>Fresh produce</h2><script>secretmarker</script>
<a href="/services/delivery">Delivery service</a><a href="mailto:help@example.org">Email</a>
<a href="tel:+911234567890">Call</a><p>Groceries and fresh produce.</p></body></html>'''


class WebsiteAnalysisTests(unittest.TestCase):
    def setUp(self):
        _audit_public.clear()
        _robots_policy.clear()
        self.addCleanup(_audit_public.clear)
        self.addCleanup(_robots_policy.clear)

    def test_extracts_page_content_without_script_text(self):
        result = extract_page(HTML, "https://example.org/")
        self.assertEqual(result["Page title"], "Example Services")
        self.assertEqual(result["Description"], "Our public service page.")
        self.assertIn("Grocery delivery", result["Headings"])
        self.assertIn("Delivery service", result["Service/product link labels"])
        self.assertEqual(result["Email links/text"], ["help@example.org"])
        self.assertEqual(result["Phone links"], ["+911234567890"])
        self.assertNotIn("secretmarker", result["On-page keyword candidates"])
        self.assertNotIn("Keyword Count", result)

    def test_url_validation_blocks_local_credentials_and_non_http(self):
        for url in ["file:///etc/passwd", "http://localhost/", "http://x.local", "https://user:password@example.org", "https://example.org:8000"]:
            with self.subTest(url=url), self.assertRaises((WebsiteError, ValueError)):
                public_url(url)
        with patch("services.website_analysis.socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 443))]):
            with self.assertRaises(WebsiteError):
                public_url("https://example.org")

    def test_robots_block_prevents_page_download(self):
        with patch("services.website_analysis.public_url", side_effect=lambda url: url), patch("services.website_analysis._read_response", return_value=(200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /")) as request:
            result = audit_website("https://example.org/")
        self.assertEqual(result["Status"], "Blocked")
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.args[0].endswith("/robots.txt"))
        self.assertNotIn("Retrieved at (UTC)", result)

    def test_success_is_timestamped_and_cached(self):
        def response(url, *args):
            return (404, {}, "") if url.endswith("/robots.txt") else (200, {"Content-Type": "text/html"}, HTML)
        with patch("services.website_analysis.public_url", side_effect=lambda url: url), patch("services.website_analysis._read_response", side_effect=response) as request:
            result = audit_website("https://example.org/")
            again = audit_website("https://example.org/")
        self.assertEqual(result["Status"], "Available")
        self.assertIn("Retrieved at (UTC)", result)
        self.assertEqual(result, again)
        self.assertEqual(request.call_count, 2)

    def test_redirect_to_private_address_is_not_fetched(self):
        def addresses(host, *args, **kwargs):
            return [(None, None, None, None, ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443))]
        def response(url, *args):
            return (404, {}, "") if url.endswith("/robots.txt") else (302, {"Location": "http://127.0.0.1/private"}, "")
        with patch("services.website_analysis.socket.getaddrinfo", side_effect=addresses), patch("services.website_analysis._read_response", side_effect=response) as request:
            result = audit_website("https://example.org/")
        self.assertEqual(result["Status"], "Unavailable")
        self.assertEqual(request.call_count, 2)
        self.assertIn("private network", result["Reason"])

    def test_missing_url_does_not_issue_requests(self):
        with patch("services.website_analysis._read_response") as request:
            result = audit_website("")
        request.assert_not_called()
        self.assertEqual(result["Status"], "Unavailable")

    def test_malformed_url_does_not_break_the_batch(self):
        with patch("services.website_analysis._read_response") as request:
            _, rows = enrich_websites({"name": "Business"}, [{"Name": "Store", "Website": "http://[invalid"}])
        request.assert_not_called()
        self.assertEqual(rows[0]["Website analysis"]["Status"], "Unavailable")

    def test_run_limit_and_reused_url(self):
        candidates = [{"Name": f"Store {i}", "Website": f"https://example{i}.org"} for i in range(MAX_SITES + 2)]
        candidates.append({"Name": "Same chain", "Website": "https://example0.org"})
        with patch("services.website_analysis.audit_website", return_value={"Status": "Available"}) as audit:
            business, rows = enrich_websites({"name": "Business", "website": ""}, candidates)
        self.assertEqual(audit.call_count, MAX_SITES + 1)  # one blank URL, eight unique URLs
        self.assertEqual(rows[-1]["Website analysis"]["Status"], "Available")
        self.assertEqual(rows[-2]["Website analysis"]["Status"], "Skipped")

    def test_non_html_response_is_unavailable(self):
        def response(url, *args):
            return (404, {}, "") if url.endswith("/robots.txt") else (200, {"Content-Type": "application/pdf"}, "PDF")
        with patch("services.website_analysis.public_url", side_effect=lambda url: url), patch("services.website_analysis._read_response", side_effect=response):
            result = audit_website("https://example.org/")
        self.assertEqual(result["Status"], "Unavailable")

    def test_retry_processes_skipped_urls_without_losing_previous_results(self):
        candidates = [{"Name": f"Store {i}", "Website": f"https://example{i}.org/"} for i in range(MAX_SITES + 2)]
        def audit(url, **kwargs):
            return {"Status": "Available", "Requested URL": url} if url else {"Status": "Unavailable"}
        with patch("services.website_analysis.audit_website", side_effect=audit):
            business, rows = enrich_websites({"name": "Business"}, candidates)
            self.assertEqual(sum(row["Website analysis"]["Status"] == "Skipped" for row in rows), 2)
            _, again = enrich_websites(business, rows)
        self.assertTrue(all(row["Website analysis"]["Status"] == "Available" for row in again))

    def test_malformed_metadata_and_oversized_headings_are_bounded(self):
        result = extract_page('<meta name="description" content><a href>Link</a><h1>' + 'x' * 1000 + '</h1>', 'https://example.org/')
        self.assertEqual(result["Description"], "")
        self.assertLessEqual(len(result["Headings"][0]), 180)


if __name__ == "__main__":
    unittest.main()
