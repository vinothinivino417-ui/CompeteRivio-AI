"""Cached, serialized geocoding for the local competitor-analysis workflow.

Public endpoint policy: https://operations.osmfoundation.org/policies/nominatim/
Requests are limited to one per second across this Python process.
"""
import threading
import time
import math

import requests
import streamlit as st
from services.alternate_geocoding import find_area_alternate


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "CompeteRivioAI-Portfolio/1.0 (business-discovery-demo)"}
_request_lock = threading.Lock()
_last_request = 0.0


@st.cache_data(ttl=86400, show_spinner=False)
def search_places(params):
    global _last_request
    with _request_lock:
        delay = 1.05 - (time.monotonic() - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()
        response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        results = response.json()
    if not isinstance(results, list) or not all(isinstance(row, dict) for row in results):
        raise ValueError("The location service returned an unexpected response. Please retry.")
    return results


def find_area(location):
    try:
        rows = search_places({"q": location.strip(), "format": "jsonv2", "addressdetails": 1, "limit": 1})
    except requests.RequestException:
        return find_area_alternate(location)
    return rows or find_area_alternate(location)


def find_nearby_places(lat, lon, tag_key, tag_value, radius):
    """One bounded best-match query; never a grid search or exhaustive POI scan."""
    delta_lat = radius / 110000
    delta_lon = radius / (110000 * max(0.01, math.cos(math.radians(lat))))
    west, east = lon - delta_lon, lon + delta_lon
    south, north = lat - delta_lat, lat + delta_lat
    if west < -180 or east > 180 or south < -90 or north > 90:
        return []
    rows = search_places({
        "q": f"[{tag_value}]", "format": "jsonv2", "limit": 20, "extratags": 1,
        "bounded": 1, "viewbox": f"{west},{south},{east},{north}",
    })
    elements = []
    for row in rows:
        if row.get("category", row.get("class")) != tag_key or row.get("type") != tag_value:
            continue
        try:
            item_lat, item_lon = float(row["lat"]), float(row["lon"])
            if not (-90 <= item_lat <= 90 and -180 <= item_lon <= 180):
                continue
            a = math.sin(math.radians(item_lat - lat) / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(item_lat)) * math.sin(math.radians(item_lon - lon) / 2) ** 2
            distance = 6371000 * 2 * math.asin(min(1, math.sqrt(a)))
            if distance > radius:
                continue
            name = row.get("name") or row.get("display_name", "").split(",")[0]
            if not name or not row.get("osm_id") or not row.get("osm_type"):
                continue
            extra = row.get("extratags") or {}
            elements.append({"id": row["osm_id"], "type": row["osm_type"],
                             "lat": item_lat, "lon": item_lon,
                             "tags": {"name": name, tag_key: tag_value, "website": extra.get("website") or extra.get("contact:website", "")},
                             "discovery_source": "OpenStreetMap nearby search (limited best matches)"})
        except (KeyError, TypeError, ValueError):
            continue
    return elements
