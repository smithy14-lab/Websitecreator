"""URL-safe slug generation with collision avoidance."""
import re

from .db import get_conn, q


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "site"


def unique_slug(name: str, exclude_lead_id: int | None = None) -> str:
    """Generate a unique slug for `name`, appending -2, -3, ... if needed."""
    base = slugify(name)
    with get_conn() as conn:
        if exclude_lead_id is not None:
            existing = {
                r["slug"]
                for r in conn.execute(
                    q("SELECT slug FROM leads WHERE slug IS NOT NULL AND id != ?"),
                    (exclude_lead_id,),
                ).fetchall()
            }
        else:
            existing = {
                r["slug"]
                for r in conn.execute(
                    "SELECT slug FROM leads WHERE slug IS NOT NULL"
                ).fetchall()
            }

    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"
