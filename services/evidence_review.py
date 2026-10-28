"""Date-based review reminders; never infer accuracy or alter evidence scores."""
from datetime import date, datetime, timedelta, timezone

from services.competitor_evidence import METRICS

INDIA_TIME = timezone(timedelta(hours=5, minutes=30))
REVIEW_DAYS = 90


def review_date():
    return datetime.now(INDIA_TIME).date()


def _date_status(raw, as_of, timestamp=False):
    if not raw:
        return "Date missing", None
    try:
        if timestamp:
            observed = datetime.fromisoformat(raw)
            if observed.tzinfo is None:
                raise ValueError()
            observed = observed.astimezone(INDIA_TIME).date()
        else:
            observed = date.fromisoformat(raw)
    except (ValueError, TypeError):
        return "Date invalid", None
    age = (as_of - observed).days
    if age < 0:
        return "Future date — check", None
    return ("Review due" if age >= REVIEW_DAYS else "Within review window"), age


def build_evidence_review(business, competitors, as_of=None):
    as_of = as_of or review_date()
    rows = []
    for reference, entity in [("B1", business)] + [(f"C{index}", item) for index, item in enumerate(competitors, 1)]:
        name = entity.get("name") if reference == "B1" else entity.get("Name")
        evidence = entity.get("User-supplied evidence (not independently verified)", {})
        evidence = evidence if isinstance(evidence, dict) else {}
        metrics = [metric for metric in METRICS if evidence.get(metric) is not None and evidence.get(metric) != ""]
        observed = evidence.get("Observed On")
        status, age = _date_status(observed, as_of) if metrics else ("No measurements", None)
        rows.append({"Reference": reference, "Business": name or "Unnamed business", "Evidence": "Manual measurements",
                     "Available measurements": ", ".join(metrics) or "None", "Recorded date": str(observed or "Unavailable"),
                     "Age (days)": age, "Review status": status, "Source": str(evidence.get("Source") or "Unavailable")})
        website = entity.get("Website analysis", {})
        website = website if isinstance(website, dict) else {}
        retrieved = website.get("Retrieved at (UTC)")
        status, age = _date_status(retrieved, as_of, timestamp=True) if website.get("Status") == "Available" else ("No usable website capture", None)
        rows.append({"Reference": reference, "Business": name or "Unnamed business", "Evidence": "Website capture",
                     "Available measurements": "Captured page text" if website.get("Status") == "Available" else "None",
                     "Recorded date": str(retrieved or "Unavailable"), "Age (days)": age, "Review status": status,
                     "Source": str(website.get("Source URL") or "Unavailable")})
    return {"As of": as_of.isoformat(), "Review after days": REVIEW_DAYS, "Rows": rows}
