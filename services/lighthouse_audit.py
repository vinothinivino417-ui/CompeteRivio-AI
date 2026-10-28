"""Read measured Lighthouse scores without running a remote audit or guessing data."""
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit


def parse_lighthouse_report(payload):
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError("Choose a Lighthouse JSON report smaller than 10 MB.")
    try:
        report = json.loads(payload)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Upload the JSON report exported by Lighthouse.") from error
    if not isinstance(report, dict):
        raise ValueError("The report must be a Lighthouse JSON object.")
    if isinstance(report.get("lighthouseResult"), dict):
        report = report["lighthouseResult"]
    if report.get("runtimeError"):
        raise ValueError("Lighthouse could not complete this audit. Run the audit again.")
    url = report.get("finalDisplayedUrl") or report.get("finalUrl") or report.get("requestedUrl")
    if not isinstance(url, str) or urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).hostname:
        raise ValueError("The report needs a valid audited HTTP(S) website URL.")
    try:
        measured = datetime.fromisoformat(report["fetchTime"].replace("Z", "+00:00"))
        if measured.tzinfo is None or measured > datetime.now(timezone.utc):
            raise ValueError()
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError("The report needs a valid audit timestamp that is not in the future.") from error
    categories = report.get("categories")
    if not report.get("lighthouseVersion") or not isinstance(categories, dict):
        raise ValueError("This file does not contain Lighthouse version and category results.")
    settings = report.get("configSettings") or {}
    if not isinstance(settings, dict):
        raise ValueError("Invalid Lighthouse device settings.")
    result = {"Website": url, "Audited at": measured.isoformat(),
              "Device": str(settings.get("formFactor", "Unknown")),
              "Lighthouse version": str(report["lighthouseVersion"])}
    for key, label in (("performance", "Performance"), ("accessibility", "Accessibility"),
                       ("best-practices", "Best practices"), ("seo", "SEO")):
        category = categories.get(key)
        score = category.get("score") if isinstance(category, dict) else None
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
                                  or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError(f"Invalid {label} score in the report.")
        result[label] = round(score * 100, 1) if score is not None else None
    if all(result[key] is None for key in ("Performance", "Accessibility", "Best practices", "SEO")):
        raise ValueError("No measured category scores were found in this audit.")
    return result
