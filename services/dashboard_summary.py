"""Small, deterministic dashboard summaries; no invented performance metrics."""
import math


def valid_distance(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def summarize_selection(rows):
    recognised = {"Direct", "Indirect", "Irrelevant"}
    classified = sum(row.get("Classification") in recognised for row in rows)
    distances = [distance for row in rows if (distance := valid_distance(row.get("Distance (km)"))) is not None]
    return {
        "selected": len(rows), "classified": classified, "unclassified": len(rows) - classified,
        "direct": sum(row.get("Classification") == "Direct" for row in rows) if classified else None,
        "indirect": sum(row.get("Classification") == "Indirect" for row in rows) if classified else None,
        "nearest": min(distances) if distances else None,
        "distance_bands": [sum(value <= 1 for value in distances), sum(1 < value <= 2 for value in distances), sum(value > 2 for value in distances)],
        "limited": any("limited best matches" in str(row.get("Discovery source", "")) for row in rows),
    }
