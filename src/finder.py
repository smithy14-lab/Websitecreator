"""Find businesses without websites.

Two paths:
  - With GOOGLE_PLACES_API_KEY set: real lead sourcing via Places API
  - Without it: load bundled sample data
"""
import os
import time
import requests

from . import storage
from .sample_data import SAMPLE_LEADS


PLACES_TEXTSEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"


def load_sample_leads() -> int:
    """Insert bundled sample leads. Returns count newly inserted."""
    storage.init_db()
    inserted = 0
    for lead in SAMPLE_LEADS:
        if storage.add_lead(lead) is not None:
            inserted += 1
    return inserted


def search_google_places(query: str, max_results: int = 20) -> list[dict]:
    """Search Google Places for businesses matching the query and filter to those
    that have no `website` field in their details.

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

    # Step 1: text search to find candidate places
    resp = requests.get(
        PLACES_TEXTSEARCH,
        params={"query": query, "key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")
    if status != "OK":
        # Google returns 200 even on errors; the real status is in the body.
        raise RuntimeError(
            f"Google Places API returned status={status}. "
            f"Message: {data.get('error_message', '(none)')}"
        )
    results = data.get("results", [])[:max_results]
    print(f"[finder] query={query!r} returned {len(results)} results", flush=True)

    # Step 2: fetch details to inspect website field
    for r in results:
        place_id = r.get("place_id")
        if not place_id:
            continue

        details_resp = requests.get(
            PLACES_DETAILS,
            params={
                "place_id": place_id,
                "fields": "name,formatted_address,formatted_phone_number,website,url,types",
                "key": api_key,
            },
            timeout=15,
        )
        details_resp.raise_for_status()
        d = details_resp.json().get("result", {})

        has_website = bool(d.get("website"))
        types = d.get("types", [])
        category = types[0].replace("_", " ").title() if types else None

        lead = {
            "business_name": d.get("name"),
            "category": category,
            "address": d.get("formatted_address"),
            "phone": d.get("formatted_phone_number"),
            "email": None,
            "has_website": has_website,
            "google_maps_url": d.get("url"),
            "source": "google_places",
        }

        if storage.add_lead(lead) is not None:
            leads_added.append(lead)

        time.sleep(0.1)

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
