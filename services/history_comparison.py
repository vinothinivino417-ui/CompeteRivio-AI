"""Compare saved selections without inferring market changes or score trends."""
from services.competitor_evidence import competitor_id, evidence_scope


def compare_saved_runs(baseline, comparison):
    left, right = baseline["snapshot"], comparison["snapshot"]
    if evidence_scope(left["business"]) != evidence_scope(right["business"]):
        raise ValueError("Choose two saved runs for the same business and mapped location.")
    def indexed(snapshot):
        result = {}
        for item in snapshot["competitors"]:
            key = competitor_id(item)
            if key in result:
                raise ValueError("A saved selection contains duplicate identifiers and cannot be compared reliably.")
            result[key] = item
        return result
    before, after = indexed(left), indexed(right)
    rows = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        status = "Added to selection" if old is None else "Removed from selection" if new is None else "Kept in selection"
        rows.append({"Competitor": (new or old).get("Name", "Unnamed"), "Identifier": key,
                     "Selection change": status,
                     "Baseline classification": old.get("Classification", "Unavailable") if old else "Not selected",
                     "Comparison classification": new.get("Classification", "Unavailable") if new else "Not selected"})
    settings = [{"Setting": label, "Baseline": left.get(key), "Comparison": right.get(key)}
                for key, label in (("category", "Industry"), ("radius_km", "Radius (km)"), ("selection_mode", "Selection mode"))]
    return {"competitors": rows, "settings": settings,
            "added": len(set(after) - set(before)), "removed": len(set(before) - set(after)),
            "retained": len(set(before) & set(after))}
