"""Conservative, explainable intent estimates for captured terms, not query data."""
import re
import unicodedata

INTENT_GROUPS = ("Branded", "Service", "Location", "Informational", "Unclassified")
GENERIC = set("the and of for hospital hospitals clinic clinics pharmacy pharmacies supermarket supermarkets super market markets store stores mart school schools restaurant restaurants cafe hotel hotels shopping mall centre center medical health healthcare limited ltd private pvt company co india indian tamil nadu road street main ward zone nagar district metropolitan area corporation city near chennai".split())
SERVICE_WORDS = set("delivery medicine medicines pharmacy prescription prescriptions grocery groceries supermarket vegetables fruits organic consultation appointments appointment treatment treatments surgery emergency care dental dentist diagnostic diagnostics blood scan scans laboratory lab vaccination vaccine vaccines physiotherapy restaurant catering menu takeaway reservation booking rooms accommodation tuition admissions education courses training coffee breakfast lunch dinner services service products product repair repairs laundry salon haircut spa".split())
INFO_WORDS = set("how why what when where guide guides tips benefits symptoms causes faq faqs tutorial tutorials prevention explained information meaning learn".split())
LOCATION_NOISE = set("the and of for ward zone road street main lane nagar district metropolitan area corporation state country near floor plot block no number".split())


def tokens(value):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", str(value)).casefold(), flags=re.UNICODE)


def estimate_intent(term, business_names=(), locations=()):
    words = tokens(term)
    observed = set(words)
    compact = "".join(words)
    brand_words = {word for name in business_names for word in tokens(name) if len(word) >= 3 and word not in GENERIC and not word.isdigit()}
    # Match a complete compact brand (D Mart / DMart), never a substring in a word.
    full_brands = {"".join(tokens(name)) for name in business_names if any(word not in GENERIC and not word.isdigit() for word in tokens(name))}
    name_forms = {"".join(tokens(name)) for name in business_names}
    geographic_parts = []
    for location in locations:
        parts = str(location).split(",")
        # OSM display addresses often begin with the store name, not a place name.
        if "".join(tokens(parts[0])) in name_forms:
            parts = parts[1:]
        geographic_parts.extend(parts)
    location_words = {word for location in geographic_parts for word in tokens(location) if len(word) >= 3 and word not in LOCATION_NOISE and not word.isdigit()}
    brand_words -= location_words
    if observed & INFO_WORDS:
        group, reason = "Informational", "Contains an informational cue: " + ", ".join(sorted(observed & INFO_WORDS))
    elif observed & brand_words or compact in full_brands:
        group, reason = "Branded", "Matches a supplied business-name clue; brand ownership is not verified."
    elif observed & location_words:
        group, reason = "Location", "Matches a supplied location clue: " + ", ".join(sorted(observed & location_words))
    elif observed & SERVICE_WORDS:
        group, reason = "Service", "Contains a service/product cue: " + ", ".join(sorted(observed & SERVICE_WORDS))
    else:
        group, reason = "Unclassified", "No reliable rule matched; keep for manual review."
    return {"Intent group (estimate)": group, "Intent reason": reason}
