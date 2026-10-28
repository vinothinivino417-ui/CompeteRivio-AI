"""Explainable local relevance estimates, not Google search prominence."""
import math
import re
import unicodedata
from urllib.parse import urlsplit


CATEGORY_TAGS = {"Hospital": ("amenity", "hospital"), "Clinic": ("amenity", "clinic"),
                 "Restaurant": ("amenity", "restaurant"), "Cafe": ("amenity", "cafe"),
                 "School": ("amenity", "school"), "Pharmacy": ("amenity", "pharmacy"),
                 "Supermarket": ("shop", "supermarket"), "Hotel": ("tourism", "hotel"),
                 "Shopping Mall": ("shop", "mall"), "Training Academy": ("amenity", "training")}
CATEGORY_TAGS.update({
    "Dentist": ("amenity", "dentist"), "Veterinary Clinic": ("amenity", "veterinary"),
    "College": ("amenity", "college"), "University": ("amenity", "university"),
    "Kindergarten": ("amenity", "kindergarten"), "Language School": ("amenity", "language_school"),
    "Driving School": ("amenity", "driving_school"), "Library": ("amenity", "library"),
    "Bakery": ("shop", "bakery"), "Grocery Store": ("shop", "convenience"),
    "Fruit & Vegetable Store": ("shop", "greengrocer"), "Butcher": ("shop", "butcher"),
    "Sweet Shop": ("shop", "confectionery"), "Fast Food": ("amenity", "fast_food"),
    "Ice Cream Shop": ("amenity", "ice_cream"), "Bar": ("amenity", "bar"),
    "Clothing Store": ("shop", "clothes"), "Shoe Store": ("shop", "shoes"),
    "Jewellery Store": ("shop", "jewelry"), "Gift Shop": ("shop", "gift"),
    "Book Store": ("shop", "books"), "Stationery Store": ("shop", "stationery"),
    "Department Store": ("shop", "department_store"), "Furniture Store": ("shop", "furniture"),
    "Hardware Store": ("shop", "hardware"), "Electronics Store": ("shop", "electronics"),
    "Mobile Phone Store": ("shop", "mobile_phone"), "Computer Store": ("shop", "computer"),
    "Optician": ("shop", "optician"), "Cosmetics Store": ("shop", "cosmetics"),
    "Hair Salon": ("shop", "hairdresser"), "Beauty Salon": ("shop", "beauty"),
    "Laundry": ("shop", "laundry"), "Dry Cleaner": ("shop", "dry_cleaning"),
    "Tailor": ("shop", "tailor"), "Florist": ("shop", "florist"),
    "Pet Store": ("shop", "pet"), "Sports Store": ("shop", "sports"),
    "Gym / Fitness Centre": ("leisure", "fitness_centre"), "Sports Centre": ("leisure", "sports_centre"),
    "Swimming Pool": ("leisure", "swimming_pool"), "Cinema": ("amenity", "cinema"),
    "Guest House": ("tourism", "guest_house"), "Hostel": ("tourism", "hostel"),
    "Travel Agency": ("shop", "travel_agency"), "Car Dealer": ("shop", "car"),
    "Car Repair": ("shop", "car_repair"), "Car Wash": ("amenity", "car_wash"),
    "Car Rental": ("amenity", "car_rental"), "Motorcycle Dealer": ("shop", "motorcycle"),
    "Bicycle Store": ("shop", "bicycle"), "Fuel Station": ("amenity", "fuel"),
    "Bank": ("amenity", "bank"), "Insurance Office": ("office", "insurance"),
    "Accountant": ("office", "accountant"), "Law Firm": ("office", "lawyer"),
    "Real Estate Agency": ("office", "estate_agent"), "Architect": ("office", "architect"),
    "IT Company": ("office", "it"), "Marketing / Advertising Agency": ("office", "advertising_agency"),
    "Courier Service": ("office", "courier"), "Post Office": ("amenity", "post_office"),
    "Digital Marketing Agency": ("office", "advertising_agency"), "Software Company": ("office", "it"),
    "Coaching Centre": ("amenity", "training"), "Computer Training Institute": ("amenity", "computer_school"),
    "Preschool": ("amenity", "kindergarten"), "Medical Laboratory": ("healthcare", "laboratory"),
})
DIRECTORY_DOMAINS = {"justdial.com", "sulekha.com", "yellowpages.com", "yelp.com", "tripadvisor.com", "indiamart.com"}


def canonical_category(value):
    label = str(value).strip()
    return next((name for name in CATEGORY_TAGS if name.casefold() == label.casefold()), label)


def category_filters(category):
    category = canonical_category(category)
    if category in {"Training Academy", "Coaching Centre", "Computer Training Institute"}:
        return (("amenity", "training"), ("amenity", "computer_school"), ("amenity", "trade_school"))
    return (CATEGORY_TAGS[category],) if category in CATEGORY_TAGS else ()


def valid_industry(value):
    return isinstance(value, str) and 1 <= len(value.strip()) <= 100 and not any(ord(c) < 32 for c in value)


def suggested_category(industry):
    if industry in CATEGORY_TAGS:
        return industry
    if re.search(r"academy|training|coaching|vocational", str(industry), re.I):
        return "Training Academy"
    for category in CATEGORY_TAGS:
        if str(industry).strip().casefold() == category.casefold():
            return category
    return str(industry).strip() if valid_industry(industry) else "Hospital"


def normalized_name(value):
    return "".join(c for c in unicodedata.normalize("NFKC", str(value)).casefold() if c.isalnum())


def same_business_listing(business, tags, distance_km):
    """Match nearby duplicate listings, including translated names with a shared URL."""
    if business.get("resolution_status") == "area_center" or distance_km > 0.05:
        return False
    own_name = normalized_name(business.get("name", ""))
    names = [tags.get(key, "") for key in ("name", "name:en", "official_name", "alt_name")]
    if own_name and any(normalized_name(name) == own_name for name in names if name):
        return True
    def website_identity(value):
        try:
            parsed = urlsplit(value if "://" in value else "https://" + value)
            return ((parsed.hostname or "").lower().removeprefix("www."), parsed.path.rstrip("/"))
        except (ValueError, TypeError):
            return ("", "")
    own_url = website_identity(business.get("website") or "")
    other_url = website_identity(tags.get("website") or tags.get("contact:website") or "")
    return bool(own_url[0] and own_url == other_url)


def remove_saved_self_listings(state):
    """Apply the own-branch filter to older saved discovery results too."""
    business = state.get("business_profile", {})
    removed = 0
    for key in ("discovered_competitors", "classified_competitors", "approved_competitors"):
        if key not in state:
            continue
        kept = []
        for row in state[key]:
            try:
                distance = float(row.get("Distance (km)"))
            except (ValueError, TypeError):
                kept.append(row)
                continue
            tags = {"name": row.get("Name", ""), "website": row.get("Website", "")}
            if math.isfinite(distance) and distance >= 0 and same_business_listing(business, tags, distance):
                removed += 1
                if key == "approved_competitors":
                    state.pop("ai_insights_report", None)
                    state.pop("ai_insights_input", None)
            else:
                kept.append(row)
        state[key] = kept
    return removed


def is_directory(name, website="", tags=None):
    tags = tags or {}
    if tags.get("information") == "directory" or tags.get("office") == "directory":
        return True
    if re.search(r"\b(?:business directory|hospital directory|yellow pages|directory listing)\b", str(name), re.I):
        return True
    try:
        host = (urlsplit(website if "://" in website else "https://" + website).hostname or "").lower().rstrip(".")
        return any(host == domain or host.endswith("." + domain) for domain in DIRECTORY_DOMAINS)
    except (TypeError, ValueError):
        return False


def valid_coordinates(latitude, longitude):
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("Enter valid latitude and longitude.")
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter valid latitude and longitude.") from error
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Enter valid latitude and longitude.")
    return lat, lon


def relevance_fields(tags, category, distance):
    if category not in CATEGORY_TAGS:
        return {"Relevance score": round(30 / (1 + distance), 2), "Relevance reason": "Custom industry has no mapped category; proximity only, category relevance unverified.", "Category evidence": "Custom industry; unverified", "Mapped category": "Unavailable", "Search prominence": "Unavailable"}
    key, expected = CATEGORY_TAGS[category]
    actual = tags.get(key)
    if (key, actual) in category_filters(category):
        match, label = 1.0, "Mapped category matches"
    elif actual:
        related = {frozenset(("hospital", "clinic")), frozenset(("restaurant", "cafe"))}
        match = 0.5 if frozenset((actual, expected)) in related else 0.0
        label = "Related mapped category" if match else "Different mapped category"
    else:
        match, label = 0.5, "Category unverified; search category used"
    score = round(70 * match + 30 / (1 + distance), 2)
    return {"Relevance score": score, "Relevance reason": f"{label}. 70 × category match (1/0.5/0) + 30 / (1 + distance in km).",
            "Category evidence": label, "Mapped category": str(actual or "Unavailable"), "Search prominence": "Unavailable"}


def ranked(rows):
    return sorted(rows, key=lambda row: (-row.get("Relevance score", 0), row.get("Distance (km)", 0), row.get("Name", "").casefold()))
