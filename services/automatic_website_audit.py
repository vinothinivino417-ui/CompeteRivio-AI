"""Bounded, keyless PageSpeed requests for already accessible public websites."""
import time

import requests
import streamlit as st

from services.lighthouse_audit import parse_lighthouse_report
from services.website_analysis import public_url


@st.cache_data(ttl=86400, max_entries=100, show_spinner=False)
def _pagespeed(url):
    # Only the fixed Google endpoint is contacted here. No credentials are sent.
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params={"url": url, "strategy": "mobile",
                    "category": ["performance", "accessibility", "best-practices", "seo"]},
            timeout=(4, 20), allow_redirects=False,
        )
        if response.status_code == 429:
            raise ValueError("Google PageSpeed quota is unavailable. Retry later or upload a Lighthouse JSON report.")
        if response.status_code != 200:
            raise ValueError(f"Google PageSpeed could not complete this audit (HTTP {response.status_code}).")
        result = parse_lighthouse_report(response.content)
        return {**result, "Status": "Available", "Source": "Google PageSpeed Insights / Lighthouse"}


def enrich_automatic_audits(business, competitors, progress=None):
    """Audit at most two unique sites; failures do not interrupt discovery/reporting."""
    results, checked, records = {}, 0, []
    started = time.monotonic()
    for index, item in enumerate([business] + competitors):
        website = item.get("Website analysis", {})
        url = website.get("Source URL", "")
        if website.get("Status") != "Available" or not url:
            audit = {"Status": "Unavailable", "Website": url,
                     "Reason": website.get("Reason", "An accessible public website is needed for an automatic audit.")}
        else:
            try:
                url = public_url(url)
                if url in results:
                    audit = results[url]
                elif checked >= 2 or time.monotonic() - started >= 45:
                    audit = {"Status": "Skipped", "Website": url,
                             "Reason": "Automatic audit limit: two unique websites per run. JSON upload remains available."}
                else:
                    checked += 1
                    name = item.get("name" if index == 0 else "Name", "Business")
                    if progress:
                        progress(f"Measuring mobile website quality for {name}...")
                    audit = _pagespeed(url)
                    results[url] = audit
            except (ValueError, TypeError, OSError, requests.RequestException) as error:
                audit = {"Status": "Unavailable", "Website": url, "Reason": str(error)}
                results[url] = audit
        records.append({**item, "Lighthouse audit": audit})
    return records[0], records[1:]
