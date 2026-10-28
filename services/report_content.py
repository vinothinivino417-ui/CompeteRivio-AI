"""Keep report observations deterministic; limit AI output to labelled suggestions."""
import json
import math
import re
from services.keyword_analysis import build_keyword_analysis

REPORT_VERSION = 7


def report_signature(business, competitors):
    return json.dumps({"report_version": REPORT_VERSION, "business": business, "competitors": competitors}, sort_keys=True)


def text(value, default="Unavailable"):
    return " ".join(str(value).split()) if value is not None and str(value).strip() else default


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_recommendations(response, competitor_count):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.IGNORECASE)
    parsed = json.loads(cleaned)
    actions = parsed.get("recommendations") if isinstance(parsed, dict) else None
    if not isinstance(actions, list) or len(actions) != 5:
        raise ValueError("Expected five recommendations")
    allowed = {"B1"} | {f"C{i + 1}" for i in range(competitor_count)}
    result = []
    for item in actions:
        if not isinstance(item, dict):
            raise ValueError("Invalid recommendation")
        action, why, refs = item.get("action"), item.get("why"), item.get("evidence_ids")
        if not all(isinstance(value, str) and 0 < len(value.strip()) <= 700 for value in (action, why)):
            raise ValueError("Invalid recommendation text")
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref in allowed for ref in refs):
            raise ValueError("Recommendation references unknown evidence")
        result.append({"action": text(action), "why": text(why), "evidence_ids": list(dict.fromkeys(refs))})
    return result


def standard_recommendations(competitor_count):
    refs = ["B1"] + (["C1"] if competitor_count else [])
    return [
        {"action": action, "why": why, "evidence_ids": refs}
        for action, why in [
            ("Verify the business name, branch, address, and operating status.", "A map listing does not establish the store format or current operations."),
            ("Check the selected businesses' actual offerings and customer overlap.", "Category and proximity estimates do not verify competitive relevance."),
            ("Collect comparable ratings and review counts with source links and observation dates.", "These measurements are needed for an evidence-based reputation comparison."),
            ("Compare like-for-like prices or service offerings through direct observation.", "A pricing advantage cannot be established from business names or locations."),
            ("Record search visibility, advertisements, and website information using consistent definitions.", "Marketing recommendations require measured activity and clearly identified evidence gaps."),
        ]
    ]


def build_grounded_report(business, competitors, recommendations=None, ai_suggestions=False):
    name = text(business.get("name"), "Your business")
    area_based = business.get("resolution_status") == "area_center"
    direct = sum(row.get("Classification") == "Direct" for row in competitors)
    indirect = sum(row.get("Classification") == "Indirect" for row in competitors)
    limited = any("limited best matches" in row.get("Discovery source", "") for row in competitors)
    lines = [
        f"# Competitive Intelligence Report: {name}",
        "## 1. Executive summary",
        f"The selected dataset contains {len(competitors)} nearby businesses: {direct} classified as direct and {indirect} as indirect competitors. Classifications and confidence are AI estimates, not verified threat levels.",
        f"Business location: {text(business.get('location'))}. [B1]",
        "The store location is unverified. Distances below are measured from the area's approximate centre, not the store. [B1]" if area_based else "Distances are straight-line estimates from the mapped business location, not travel distances. [B1]",
        "Discovery used a limited best-match fallback. The list is not exhaustive." if limited else "The report covers the selected businesses; it does not establish complete market coverage.",
        "## 2. Competitive strengths supported by evidence",
        "Business names, map categories, and distances do not establish advantages in pricing, size, product range, customer loyalty, foot traffic, or operational performance. Any supplied measurements are listed in the evidence register below.",
        "## 3. Evidence gaps and limitations",
        "Store format, customer behaviour, pricing strategy, market share, foot traffic, and commercial performance are not established by the supplied map listings. Missing evidence is a limitation of this analysis, not a verified business weakness.",
        "User-entered measurements are not independently verified. A blank or missing value means unavailable, not zero. AI classification reasons are interpretations and are not treated as factual evidence.",
        "## 4. Opportunities to investigate",
        "Use the validation actions below to gather evidence before deciding whether pricing, service, positioning, or marketing changes are justified. No commercial opportunity is confirmed by proximity alone.",
        "## 5. Competitor assessment",
    ]
    for i, row in enumerate(competitors, 1):
        distance = number(row.get("Distance (km)"))
        distance_label = f"{distance:.2f} km" if distance is not None else "Unavailable"
        lines.append(f"- **{text(row.get('Name'))}**: category {text(row.get('Category'))}; distance {distance_label}; classification {text(row.get('Classification'))}; classification confidence {text(row.get('Confidence'))}. Competitive threat is unverified. [C{i}]")
    keywords = build_keyword_analysis(business, competitors)
    if keywords["Terms"]:
        lines.extend(["## Captured website terms and possible content gaps",
                      "This compares extracted page terms and declared meta keywords only. Search volume and Google rankings are unavailable. Intent groups are conservative rule-based estimates, not observed search behaviour. A term missing from the captured sample may still appear elsewhere on the website."])
        lines.append("Estimated intent clusters (business-name/location/cue-word rules; review required):")
        for entity in keywords["Entities"]:
            if entity["Usable"]:
                summary = "; ".join(f"{group}: {len(values)} captured terms" for group, values in entity["Intent groups"].items() if values)
                lines.append(f"- {text(entity['Label'])}: {summary}. Source: {text(entity['Source URL'])}; retrieved: {text(entity['Retrieved at (UTC)'])}. [{entity['Evidence ID']}]")
        if not keywords["Entities"][0]["Usable"]:
            lines.append("Your business has no usable captured terms, so content gaps cannot be determined.")
        elif keywords["Potential gaps"]:
            for gap in keywords["Potential gaps"][:10]:
                lines.append(f"- Term to review: {gap['Term']}. Captured for {gap['Captured for competitors']}, not in your captured sample. References: B1, {gap['Evidence references']}. This is a potential content gap, not a verified SEO opportunity.")
        else:
            lines.append("No potential gaps were identified in the captured samples. This does not establish complete content coverage.")
    lines.extend([
        "## 6. Five prioritized validation actions",
        "The following AI suggestions are unverified proposals, not findings. Validate them before acting." if ai_suggestions else "These standard validation steps are based on the available evidence gaps; they do not assert additional facts about the business.",
    ])
    for i, item in enumerate(recommendations or standard_recommendations(len(competitors)), 1):
        lines.append(f"{i}. **{item['action']}** {item['why']} References: {', '.join(item['evidence_ids'])}.")
    lines.append("## Evidence register")
    lines.extend([
        f"### B1 - {name}",
        f"Source: {text(business.get('source'))}. Location: {text(business.get('location'))}.",
        f"Coordinate basis: {text(business.get('coordinate_accuracy'), 'Mapped listing; not independently verified')}.",
    ])
    entities = [("B1", business)] + [(f"C{i}", item) for i, item in enumerate(competitors, 1)]
    for reference, item in entities:
        if reference != "B1":
            lines.extend([f"### {reference} - {text(item.get('Name'))}", f"Listing source: {text(item.get('Discovery source'), 'OpenStreetMap')}. OSM identifier: {text(item.get('OSM Type'))} {text(item.get('OSM ID'))}."])
        website = item.get("Website analysis", {})
        if website:
            lines.append(f"Website check: {text(website.get('Status'))}. Source URL: {text(website.get('Source URL'))}.")
            if website.get("Status") == "Available":
                lines.append(f"Retrieved at (UTC): {text(website.get('Retrieved at (UTC)'))}. Scope: {text(website.get('Scope'))}.")
                lines.append(f"Page title (website text): {text(website.get('Page title'), 'Not found in fetched HTML')}.")
                lines.append(f"Description (website text): {text(website.get('Description'), 'Not found in fetched HTML')}.")
                for field in ("Headings", "Service/product link labels", "On-page keyword candidates", "Email links/text", "Phone links"):
                    lines.append(f"- {field}: {text('; '.join(website.get(field, [])), 'Not found in fetched HTML')}.")
                lines.append("Website content is self-published; ownership and branch identity are unverified. On-page words do not establish search demand or verified service offerings.")
            else:
                lines.append(f"Website information is unavailable: {text(website.get('Reason'), 'Not checked')}.")
        audit = item.get("Lighthouse audit", {})
        if audit:
            if audit.get("Status") == "Available":
                lines.append(f"Mobile website audit: {text(audit.get('Source'))}. Website: {text(audit.get('Website'))}. Audited at: {text(audit.get('Audited at'))}.")
                lines.append("Lighthouse lab scores out of 100: " + "; ".join(f"{metric}: {text(audit.get(metric))}" for metric in ("Performance", "Accessibility", "Best practices", "SEO")) + ". These are page-level technical checks, not Google rankings or competitor strength scores.")
            else:
                lines.append(f"Website quality audit: {text(audit.get('Status'))}. {text(audit.get('Reason'))}")
        evidence = item.get("User-supplied evidence (not independently verified)", {})
        if isinstance(evidence, dict) and any(metric in evidence for metric in ("Rating", "Review Count", "Active Ads", "Keyword Count")):
            lines.append("User-supplied measurements (not independently verified):")
            for metric in ("Rating", "Review Count", "Active Ads", "Keyword Count"):
                lines.append(f"- {metric}: {text(evidence.get(metric))}.")
            lines.append(f"Measurement source: {text(evidence.get('Source'))}. Observed on: {text(evidence.get('Observed On'))}.")
        else:
            lines.append("Ratings, review counts, active ads, and keyword counts: Unavailable in the supplied evidence.")
        scoring = item.get("Partial evidence scoring", {})
        score = number(scoring.get("Evidence score")) if isinstance(scoring, dict) else None
        if isinstance(scoring, dict) and scoring.get("Applied weights"):
            lines.append(f"Applied relative weights: {text(json.dumps(scoring.get('Applied weights', {}), ensure_ascii=False))}. Chosen-weight coverage: {text(scoring.get('Selected weight coverage (%)'))}%.")
        if score is None:
            lines.append("Evidence score: Unavailable - insufficient comparable measurements.")
        else:
            lines.append(f"Partial evidence score: {score:.2f}/100. Planned scoring-weight coverage: {text(scoring.get('PRD weight coverage (%)'))}%. This is not a full competitive strength score.")
            lines.append(f"Category breakdown: {text(json.dumps(scoring.get('Breakdown', {}), ensure_ascii=False))}.")
            lines.append(f"Category contributions to the score: {text(json.dumps(scoring.get('Category contributions', {}), ensure_ascii=False))}.")
            if reference == "B1" and scoring.get("Gap vs competitor average") is not None:
                lines.append(f"Partial score gap versus the selected competitor average: {scoring['Gap vs competitor average']:+.2f} points. This is a relative evidence comparison, not a measured commercial advantage.")
    return "\n\n".join(lines)
