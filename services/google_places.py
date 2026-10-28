"""Optional, uncached Google Places ratings. No key means no paid requests."""
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import unicodedata

from dotenv import load_dotenv
import requests


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join("places." + field for field in (
    "id", "displayName", "formattedAddress", "location", "rating", "userRatingCount",
    "googleMapsUri", "attributions"))


def is_configured():
    return bool(os.getenv("GOOGLE_PLACES_API_KEY", "").strip())


def _name(value):
    return "".join(c for c in unicodedata.normalize("NFKC", str(value)).casefold() if c.isalnum())


def _coordinates(latitude, longitude):
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("Invalid mapped coordinates.")
    lat, lon = float(latitude), float(longitude)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid mapped coordinates.")
    return lat, lon


def _distance(lat, lon, other_lat, other_lon):
    first, second = math.radians(lat), math.radians(other_lat)
    delta_lat, delta_lon = second - first, math.radians(other_lon - lon)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(first) * math.cos(second) * math.sin(delta_lon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(max(0, value))))


def fetch_google_rating(name, latitude, longitude):
    """One billed Text Search; accept a unique exact-name match within 200m only."""
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    base = {"Requested business": str(name), "Source": "Google Maps"}
    if not key:
        return {**base, "Status": "Not configured", "Note": "Set GOOGLE_PLACES_API_KEY on the machine running the app."}
    try:
        lat, lon = _coordinates(latitude, longitude)
        if not isinstance(name, str) or not _name(name):
            raise ValueError("A business name is required.")
    except (TypeError, ValueError):
        return {**base, "Status": "Unavailable", "Note": "A business name and valid mapped coordinates are required."}
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(ENDPOINT,
                headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS},
                json={"textQuery": name, "pageSize": 3,
                      "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 500.0}}},
                timeout=(3, 8), allow_redirects=False)
        if response.status_code != 200:
            notes = {400: "Check that Places API (New) is enabled and the request is supported.",
                     401: "Check the API key configuration.",
                     403: "Check the key restrictions, Places API (New) access and Google Cloud billing.",
                     429: "Google quota or rate limit reached. Retry later."}
            return {**base, "Status": "Unavailable", "Note": notes.get(response.status_code, "Google Places is temporarily unavailable.")}
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("places", []), list):
            raise ValueError("Invalid response")
        matches = {}
        for place in payload.get("places", []):
            if not isinstance(place, dict):
                continue
            display = place.get("displayName", {})
            location = place.get("location", {})
            if not isinstance(display, dict) or not isinstance(location, dict):
                continue
            try:
                other_lat, other_lon = _coordinates(location.get("latitude"), location.get("longitude"))
            except (TypeError, ValueError):
                continue
            if _name(display.get("text", "")) == _name(name) and _distance(lat, lon, other_lat, other_lon) <= 200 and isinstance(place.get("id"), str):
                matches[place["id"]] = place
        if len(matches) != 1:
            return {**base, "Status": "Needs review", "Note": "No unique exact-name Google match within 200 m. No ratings were assigned to this listing."}
        place = next(iter(matches.values()))
        rating, count = place.get("rating"), place.get("userRatingCount")
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, (int, float)) or not math.isfinite(rating) or not 0 <= rating <= 5):
            raise ValueError("Invalid rating")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise ValueError("Invalid review count")
        return {**base, "Status": "Available" if rating is not None or count is not None else "No measurements",
                "Google business": place["displayName"]["text"], "Address": place.get("formattedAddress", ""),
                "Rating": rating, "Review Count": count,
                "Google Maps URL": "https://www.google.com/maps/search/?api=1&query=place&query_place_id=" + requests.utils.quote(place["id"], safe=""),
                "Retrieved at (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "Attributions": place.get("attributions", []),
                "Note": "Exact name and proximity match; verify the address and branch. Missing measurements are not zero."}
    except (requests.RequestException, ValueError, TypeError, KeyError):
        # Never show a raw exception or provider error body that might contain credentials.
        return {**base, "Status": "Unavailable", "Note": "Google Places request failed or returned invalid data. Your free analysis is unchanged."}
