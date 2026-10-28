"""Compare captured webpage terms without inventing SEO rankings or demand."""
from collections import Counter
import unicodedata
from services.keyword_intent import estimate_intent, INTENT_GROUPS


def captured_terms(audit):
    if not isinstance(audit, dict) or audit.get("Status") != "Available" or not audit.get("Source URL") or not audit.get("Retrieved at (UTC)"):
        return set()
    terms = set()
    for field in ("On-page keyword candidates", "Declared meta keywords"):
        values = audit.get(field, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            term = " ".join(unicodedata.normalize("NFKC", value).casefold().split()).strip(" ,;.")
            if 1 < len(term) <= 100:
                terms.add(term)
    return terms


def build_keyword_analysis(business, competitors):
    names = Counter(item.get("Name", "Business") for item in competitors)
    entities = []
    for index, item in enumerate([business] + competitors):
        name = item.get("name" if index == 0 else "Name", "Business")
        audit = item.get("Website analysis", {})
        audit = audit if isinstance(audit, dict) else {}
        terms = captured_terms(audit)
        reference = "B1" if index == 0 else f"C{index}"
        label = f"Your business: {name}" if index == 0 else f"{name} [{reference}]" if names[name] > 1 else name
        entities.append({"Evidence ID": reference, "Name": name, "Label": label, "Terms": terms,
                         "Usable": bool(terms), "Website status": audit.get("Status", "Not checked"),
                         "Source URL": audit.get("Source URL", ""), "Retrieved at (UTC)": audit.get("Retrieved at (UTC)", ""),
                         "Note": audit.get("Reason", "No terms captured from this HTML page." if not terms else "Sampled page terms only")})
    own = entities[0]
    counts = Counter(term for entity in entities for term in entity["Terms"])
    terms = sorted(counts, key=lambda term: (-counts[term], term))
    rows, observations = [], []
    intent_counts = []
    business_names = [business.get("name", "")] + [item.get("Name", "") for item in competitors]
    locations = [business.get("location", "")] + [item.get("Address", "") for item in competitors]
    intents = {term: estimate_intent(term, business_names, locations) for term in terms}
    for entity in entities:
        entity["Intent groups"] = {group: sorted(term for term in entity["Terms"] if intents[term]["Intent group (estimate)"] == group) for group in INTENT_GROUPS}
        if entity["Usable"]:
            intent_counts.extend({"Business": entity["Label"], "Evidence ID": entity["Evidence ID"], "Intent group (estimate)": group, "Captured terms": len(entity["Intent groups"][group])} for group in INTENT_GROUPS)
    for term in terms:
        observed = [entity for entity in entities[1:] if term in entity["Terms"]]
        if not own["Usable"]:
            focus = "Your page unavailable"
        elif term not in own["Terms"] and observed:
            focus = "Potential content gap"
        elif observed:
            focus = "Shared captured term"
        else:
            focus = "Captured on your page"
        rows.append({"Term": term, **intents[term],
                     "Your captured terms": "Unavailable" if not own["Usable"] else "Captured" if term in own["Terms"] else "Not captured",
                     "Competitor observations": len(observed),
                     "Captured for competitors": "; ".join(entity["Label"] for entity in observed),
                     "Review": focus,
                     "Evidence references": ", ".join(entity["Evidence ID"] for entity in entities if term in entity["Terms"])})
        for entity in entities:
            if term in entity["Terms"]:
                observations.append({"Term": term, **intents[term], "Business": entity["Name"], "Evidence ID": entity["Evidence ID"],
                                     "Source URL": entity["Source URL"], "Retrieved at (UTC)": entity["Retrieved at (UTC)"]})
    return {"Entities": entities, "Terms": terms, "Rows": rows, "Observations": observations, "Intent counts": intent_counts,
            "Potential gaps": [row for row in rows if row["Review"] == "Potential content gap"]}
