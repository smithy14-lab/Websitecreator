"""Find businesses via Google Places API (New)."""
import os
import requests

from . import storage


PLACES_SEARCH_TEXT = "https://places.googleapis.com/v1/places:searchText"


def search_google_places(query: str, max_results: int = 20) -> list[dict]:
    """Search Google Places (New API) for businesses matching the query.

    Example queries:
        "plumber in Austin, TX"
        "restaurant in Brooklyn, NY"
        "auto repair near Newark, NJ"
    """
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set in .env")

    storage.init_db()
    leads_added = []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri,places.googleMapsUri,"
            "places.types"
        ),
    }
    body = {"textQuery": query, "maxResultCount": min(max_results, 20)}

    resp = requests.post(PLACES_SEARCH_TEXT, json=body, headers=headers, timeout=15)
    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(
            f"Google Places API error (HTTP {resp.status_code}): {err}"
        )

    places = resp.json().get("places", [])
    print(f"[finder] query={query!r} returned {len(places)} places", flush=True)

    for p in places:
        name = (p.get("displayName") or {}).get("text")
        if not name:
            continue
        has_website = bool(p.get("websiteUri"))
        types = p.get("types", [])
        category = types[0].replace("_", " ").title() if types else None

        lead = {
            "business_name": name,
            "category": category,
            "address": p.get("formattedAddress"),
            "phone": p.get("nationalPhoneNumber"),
            "email": None,
            "has_website": has_website,
            "google_maps_url": p.get("googleMapsUri"),
            "source": "google_places",
        }

        if storage.add_lead(lead) is not None:
            leads_added.append(lead)

    return leads_added
