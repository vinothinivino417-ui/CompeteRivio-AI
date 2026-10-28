"""User-supplied evidence and comparable, explicitly partial scores. No paid APIs."""
import hashlib
import json
import math
from datetime import date


METRICS = {"Rating": (0, 5), "Review Count": (0, None), "Active Ads": (0, None), "Keyword Count": (0, None)}
CATEGORIES = {"Reputation": (20, ("Rating", "Review Count")), "Paid activity": (15, ("Active Ads",)), "Keyword strategy": (15, ("Keyword Count",))}
DEFAULT_WEIGHTS = {"Search visibility": 25, "Reputation": 20, "Paid activity": 15, "Keyword strategy": 15,
                   "Social presence": 10, "Website quality": 10, "Local presence": 5}
WEIGHT_PRESETS = {
    "Default": DEFAULT_WEIGHTS,
    "Retail": {"Search visibility": 20, "Reputation": 25, "Paid activity": 15, "Keyword strategy": 10, "Social presence": 10, "Website quality": 10, "Local presence": 10},
    "Healthcare": {"Search visibility": 15, "Reputation": 30, "Paid activity": 5, "Keyword strategy": 10, "Social presence": 5, "Website quality": 15, "Local presence": 20},
    "Restaurants": {"Search visibility": 15, "Reputation": 30, "Paid activity": 10, "Keyword strategy": 10, "Social presence": 10, "Website quality": 5, "Local presence": 20},
}


def validate_weights(weights=None):
    if weights is not None and not isinstance(weights, dict):
        raise ValueError("Scoring weights must be a category-to-weight mapping.")
    if set(weights or {}) - set(DEFAULT_WEIGHTS):
        raise ValueError("Unknown scoring category.")
    configured = {**DEFAULT_WEIGHTS, **(weights or {})}
    result = {}
    for category, raw in configured.items():
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid weight for {category}.") from None
        if isinstance(raw, bool) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"Weight for {category} must be between 0 and 100.")
        result[category] = int(value) if value.is_integer() else value
    if sum(result.values()) <= 0:
        raise ValueError("At least one category must have a positive weight.")
    return result


def weights_for_business(business, settings=None):
    return validate_weights((settings or {}).get(evidence_scope(business)))


def evidence_scope(business):
    return json.dumps([business.get(key) for key in ("name", "osm_type", "osm_id", "latitude", "longitude")])


def competitor_id(item):
    if item.get("OSM ID") is not None and item.get("OSM Type"):
        return f"{item['OSM Type']}:{item['OSM ID']}"
    identity = json.dumps([item.get(key) for key in ("Name", "Latitude", "Longitude")])
    return "listing:" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def build_targets(business, approved):
    return [{"Target ID": "business", "Name": business.get("name", "Your business")}] + [
        {"Target ID": competitor_id(item), "Name": item["Name"]} for item in approved
    ]


def validate_evidence(rows, allowed_ids):
    """Validate all rows before applying any changes. Blank rows clear evidence."""
    result = {}
    for row in rows:
        target_id = str(row.get("Target ID", "")).strip()
        if target_id not in allowed_ids:
            raise ValueError(f"Unknown Target ID: {target_id}. Use the downloaded template.")
        if target_id in result:
            raise ValueError(f"Duplicate Target ID: {target_id}")
        entry = {}
        for metric, (minimum, maximum) in METRICS.items():
            raw = row.get(metric)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{target_id}: {metric} must be a number.") from None
            if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
                raise ValueError(f"{target_id}: invalid {metric}.")
            if metric != "Rating" and not number.is_integer():
                raise ValueError(f"{target_id}: {metric} must be a whole number.")
            entry[metric] = number if metric == "Rating" else int(number)
        if entry:
            source = str(row.get("Source", "") or "").strip()
            observed = str(row.get("Observed On", "") or "").strip()
            if not source:
                raise ValueError(f"{target_id}: add a source URL or evidence description.")
            try:
                observed_date = date.fromisoformat(observed)
            except ValueError:
                raise ValueError(f"{target_id}: Observed On must be YYYY-MM-DD.") from None
            if observed_date > date.today():
                raise ValueError(f"{target_id}: observation date cannot be in the future.")
            entry.update({"Source": source, "Observed On": observed_date.isoformat()})
        result[target_id] = entry
    return result


def calculate_scores(targets, evidence, weights=None):
    """Use the SAME complete categories for every business in the comparison."""
    configured = validate_weights(weights)
    active = {
        category: (configured[category], metrics) for category, (_, metrics) in CATEGORIES.items()
        if configured[category] > 0 and len(targets) >= 2 and all(
            metric in evidence.get(target["Target ID"], {}) for target in targets for metric in metrics
        )
    }
    coverage = sum(weight for weight, _ in active.values())
    default_coverage = sum(DEFAULT_WEIGHTS[category] for category in active)
    selected_coverage = round(coverage / sum(configured.values()) * 100, 2)
    normalized = {}
    for _, metrics in active.values():
        for metric in metrics:
            values = [evidence[target["Target ID"]][metric] for target in targets]
            low, high = min(values), max(values)
            normalized[metric] = [50.0 if high == low else (value - low) / (high - low) * 100 for value in values]
    scores = []
    for index, target in enumerate(targets):
        breakdown = {
            category: round(sum(normalized[metric][index] for metric in metrics) / len(metrics), 2)
            for category, (_, metrics) in active.items()
        }
        score = sum(breakdown[category] * weight for category, (weight, _) in active.items()) / coverage if coverage else None
        scores.append({**target, "Evidence score": round(score, 2) if score is not None else None,
                       "PRD weight coverage (%)": default_coverage,
                       "Selected weight coverage (%)": selected_coverage,
                       "Applied weights": dict(configured), "Breakdown": breakdown,
                       "Included weight shares (%)": {category: round(weight / coverage * 100, 2) for category, (weight, _) in active.items()},
                       "Category contributions": {category: round(breakdown[category] * weight / coverage, 2) for category, (weight, _) in active.items()}})
    if scores:
        comparable = [row["Evidence score"] for row in scores[1:] if row["Evidence score"] is not None]
        scores[0]["Gap vs competitor average"] = round(scores[0]["Evidence score"] - sum(comparable) / len(comparable), 2) if scores[0]["Evidence score"] is not None and comparable else None
    return scores


def enrich_report_inputs(business, approved, saved, scoring_settings=None):
    evidence = saved.get(evidence_scope(business), {})
    targets = build_targets(business, approved)
    scores = {row["Target ID"]: row for row in calculate_scores(targets, evidence, weights_for_business(business, scoring_settings))}
    def enriched(item, target_id):
        return {**item, "User-supplied evidence (not independently verified)": evidence.get(target_id, {}),
                "Partial evidence scoring": scores[target_id]}
    return enriched(business, "business"), [enriched(item, competitor_id(item)) for item in approved]
