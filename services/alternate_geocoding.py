"""One cached Photon locality lookup; no POI scan or automatic first-result acceptance."""
import threading
import time
import requests
import streamlit as st

from services.candidate_rules import valid_coordinates, normalized_name

_lock = threading.Lock()
_last_request = 0.0


@st.cache_data(ttl=86400, max_entries=100, show_spinner=False)
def find_area_alternate(location):
    global _last_request
    with _lock:
        delay = max(0, 1.05 - (time.monotonic() - _last_request))
        if delay:
            time.sleep(delay)
        _last_request = time.monotonic()
        response = requests.get("https://photon.komoot.io/api/", params={"q": location.strip(), "limit": 5},
                                headers={"User-Agent": "CompeteRivioAI-Portfolio/1.0"}, timeout=(4, 8))
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise ValueError("The alternate location service returned invalid results.")
    candidates = []
    requested = normalized_name(location.split(",")[0])
    for feature in data["features"]:
        if not isinstance(feature, dict):
            continue
        properties, geometry = feature.get("properties", {}), feature.get("geometry", {})
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue
        if properties.get("osm_key") != "place" or properties.get("osm_value") not in {"suburb", "neighbourhood", "quarter", "village", "town", "city", "hamlet", "borough", "municipality"}:
            continue
        name = properties.get("name")
        coordinates = geometry.get("coordinates", [])
        if not isinstance(name, str) or geometry.get("type") != "Point" or not isinstance(coordinates, list) or len(coordinates) != 2:
            continue
        try:
            lat, lon = valid_coordinates(coordinates[1], coordinates[0])
        except ValueError:
            continue
        parts = list(dict.fromkeys(str(properties[key]) for key in ("name", "district", "city", "state", "country") if properties.get(key)))
        country = properties.get("countrycode", "").upper()
        if "india" in location.casefold() and country != "IN":
            continue
        candidates.append((normalized_name(name) != requested, {"name": name, "display_name": ", ".join(parts), "lat": str(lat), "lon": str(lon), "_geocoder": "Photon / OpenStreetMap", "type": properties["osm_value"]}))
    return [candidate for _, candidate in sorted(candidates, key=lambda row: row[0])[:3]]
