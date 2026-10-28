"""Display sourced observations without synthesizing ad activity or history."""
from collections import Counter
from datetime import date
import math

from services.competitor_evidence import evidence_scope, build_targets


def observed_ad_count(entry):
    if not isinstance(entry, dict) or not str(entry.get("Source", "") or "").strip() or not entry.get("Observed On"):
        return None
    try:
        observed = date.fromisoformat(entry["Observed On"])
        if observed > date.today():
            return None
        raw = entry.get("Active Ads")
        if raw is None or isinstance(raw, bool) or str(raw).strip() == "":
            return None
        count = float(raw)
        return int(count) if math.isfinite(count) and count >= 0 and count.is_integer() else None
    except (TypeError, ValueError):
        return None


def build_marketing_evidence(business, competitors, saved):
    evidence = saved.get(evidence_scope(business), {})
    names = Counter(item.get("Name", "Business") for item in competitors)
    result = []
    for index, (item, target) in enumerate(zip([business] + competitors, build_targets(business, competitors))):
        entry = evidence.get(target["Target ID"], {})
        count = observed_ad_count(entry)
        audit = item.get("Website analysis", {})
        audit = audit if isinstance(audit, dict) else {}
        available = audit.get("Status") == "Available" and bool(audit.get("Source URL")) and bool(audit.get("Retrieved at (UTC)"))
        name = target["Name"]
        label = f"Your business: {name}" if index == 0 else f"{name} [C{index}]" if names[name] > 1 else name
        result.append({"Business": name, "Label": label, "Target ID": target["Target ID"],
                       "Active Ads": count,
                       "Ad-count source": str(entry.get("Source", "")) if count is not None else "",
                       "Ad-count observed on": entry.get("Observed On", "") if count is not None else "",
                       "Ad-count status": "User-provided observation" if count is not None else "Unavailable - add a count, source, and observation date",
                       "Website status": "Available" if available else "Unavailable - missing source or retrieval time" if audit.get("Status") == "Available" else audit.get("Status", "Not checked"),
                       "Website evidence usable": bool(available),
                       "Webpage title": audit.get("Page title", "") if available else "",
                       "Webpage description": audit.get("Description", "") if available else "",
                       "Website headings": "; ".join(audit.get("Headings", [])) if available else "",
                       "Service/product link labels": "; ".join(audit.get("Service/product link labels", [])) if available else "",
                       "Website source URL": audit.get("Source URL", ""),
                       "Website retrieved at (UTC)": audit.get("Retrieved at (UTC)", "") if available else "",
                       "Website note": "Self-published page text; not a paid advertisement or verified branch offering" if available else audit.get("Reason", "No usable website evidence")})
    return result
