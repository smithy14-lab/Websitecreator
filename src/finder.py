"""Find businesses without websites.

Two paths:
  - With GOOGLE_PLACES_API_KEY set: real lead sourcing via Places API (New)
  - Without it: load bundled sample data
"""
import os
import requests

from . import storage
from .sample_data import SAMPLE_LEADS


PLACES_SEARCH_TEXT = "https://places.googleapis.com/v1/places:searchText"


def load_sample_leads() -> int:
    """Insert bundled sample leads. Returns count newly inserted."""
    storage.init_db()
    inserted = 0
    for lead in SAMPLE_LEADS:
        if storage.add_lead(lead) is not None:
            inserted += 1
    return inserted


def search_google_places(query: str, max_results: int = 20) -> list[dict]:
    """Search Google Places (New API) for businesses matching the query.

    Example queries:
        "plumber in Austin, TX"
        "restaurant in Brooklyn, NY"
        "auto repair near Newark, NJ"
    """
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_PLACES_API_KEY not set. Either set it in .env or use "
            "load_sample_leads() instead."
        )

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


def find_leads(query: str | None = None, max_results: int = 20) -> int:
    """Convenience wrapper. Returns count of leads added.

    If query provided + API key set → real search.
    Otherwise → load sample data.
    """
    if query and os.environ.get("GOOGLE_PLACES_API_KEY"):
        results = search_google_places(query, max_results=max_results)
        return len(results)
    return load_sample_leads()
