"""Lead storage. Works against SQLite (dev) or Postgres (prod) via db.py."""
import json
from datetime import datetime, timezone

from .db import IS_POSTGRES, autoincrement_pk, get_conn, q, row_to_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA_LEADS = f"""
CREATE TABLE IF NOT EXISTS leads (
    id {autoincrement_pk()},
    business_name TEXT NOT NULL,
    category TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    has_website INTEGER DEFAULT 0,
    google_maps_url TEXT,
    source TEXT,
    status TEXT DEFAULT 'new',
    site_html TEXT,
    site_copy_json TEXT,
    email_pitch TEXT,
    phone_script TEXT,
    notes TEXT,
    slug TEXT,
    subscription_status TEXT DEFAULT 'inactive',
    plan TEXT DEFAULT 'basic',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    custom_domain TEXT,
    subscribed_at TEXT,
    extra_pages_json TEXT,
    site_kind TEXT DEFAULT 'single',
    created_at TEXT,
    contacted_at TEXT,
    UNIQUE(business_name, address)
);
"""

SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_has_website ON leads(has_website);
CREATE UNIQUE INDEX IF NOT EXISTS idx_slug ON leads(slug) WHERE slug IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_domain ON leads(custom_domain) WHERE custom_domain IS NOT NULL;
"""

# Columns that may need to be added to a pre-existing leads table.
MIGRATION_COLUMNS = [
    ("slug", "TEXT"),
    ("subscription_status", "TEXT DEFAULT 'inactive'"),
    ("plan", "TEXT DEFAULT 'basic'"),
    ("stripe_customer_id", "TEXT"),
    ("stripe_subscription_id", "TEXT"),
    ("custom_domain", "TEXT"),
    ("subscribed_at", "TEXT"),
    ("extra_pages_json", "TEXT"),
    ("site_kind", "TEXT DEFAULT 'single'"),
]


def init_db():
    with get_conn() as conn:
        conn.execute(SCHEMA_LEADS)
        _migrate_columns(conn)
        for stmt in SCHEMA_INDEXES.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
    _backfill_slugs()


def _backfill_slugs() -> None:
    """Assign slugs to any lead with a generated site but no slug yet."""
    from .slugs import unique_slug  # avoid circular import at module load
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, business_name FROM leads "
            "WHERE site_html IS NOT NULL AND (slug IS NULL OR slug = '')"
        ).fetchall()
    for r in rows:
        r = row_to_dict(r)
        set_slug(r["id"], unique_slug(r["business_name"], exclude_lead_id=r["id"]))


def _migrate_columns(conn) -> None:
    """Add columns introduced after initial schema. Idempotent."""
    if IS_POSTGRES:
        existing = {
            r["column_name"]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'leads'"
            ).fetchall()
        }
    else:
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
    for col, decl in MIGRATION_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {decl}")


def add_lead(lead: dict) -> int | None:
    """Insert a lead. Returns row id, or None if duplicate."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                q(
                    """
                    INSERT INTO leads (business_name, category, address, phone, email,
                                       has_website, google_maps_url, source, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                    RETURNING id
                    """
                ),
                (
                    lead["business_name"],
                    lead.get("category"),
                    lead.get("address"),
                    lead.get("phone"),
                    lead.get("email"),
                    1 if lead.get("has_website") else 0,
                    lead.get("google_maps_url"),
                    lead.get("source", "manual"),
                    _now(),
                ),
            ).fetchone()
            return row["id"] if row else None
    except Exception as e:
        # UniqueViolation on either driver maps to a duplicate lead.
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            return None
        raise


def list_leads(only_no_website: bool = True, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM leads WHERE 1=1"
    args: list = []
    if only_no_website:
        sql += " AND has_website = 0"
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        return [row_to_dict(r) for r in conn.execute(q(sql), args).fetchall()]


def get_lead(lead_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(q("SELECT * FROM leads WHERE id = ?"), (lead_id,)).fetchone()
        return row_to_dict(row) if row else None


def get_lead_by_slug(slug: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(q("SELECT * FROM leads WHERE slug = ?"), (slug,)).fetchone()
        return row_to_dict(row) if row else None


def get_lead_by_domain(domain: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            q("SELECT * FROM leads WHERE custom_domain = ?"), (domain,)
        ).fetchone()
        return row_to_dict(row) if row else None


def update_lead(lead_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    args = list(fields.values()) + [lead_id]
    with get_conn() as conn:
        conn.execute(q(f"UPDATE leads SET {cols} WHERE id = ?"), args)


def mark_contacted(lead_id: int, status: str = "contacted") -> None:
    update_lead(lead_id, status=status, contacted_at=_now())


def save_generated(
    lead_id: int,
    site_html: str,
    site_copy: dict,
    email_pitch: str,
    phone_script: str,
    extra_pages: dict | None = None,
    site_kind: str = "single",
) -> None:
    fields = dict(
        site_html=site_html,
        site_copy_json=json.dumps(site_copy),
        email_pitch=email_pitch,
        phone_script=phone_script,
        site_kind=site_kind,
        extra_pages_json=json.dumps(extra_pages) if extra_pages else None,
    )
    update_lead(lead_id, **fields)


def set_custom_domain(lead_id: int, domain: str | None) -> None:
    update_lead(lead_id, custom_domain=domain)


def set_slug(lead_id: int, slug: str) -> None:
    update_lead(lead_id, slug=slug)


def set_subscription(
    lead_id: int,
    status: str,
    plan: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> None:
    fields = {"subscription_status": status}
    if status == "active":
        fields["subscribed_at"] = _now()
    if plan:
        fields["plan"] = plan
    if stripe_customer_id:
        fields["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        fields["stripe_subscription_id"] = stripe_subscription_id
    update_lead(lead_id, **fields)


def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM leads").fetchone()
        no_site = conn.execute(
            "SELECT COUNT(*) AS c FROM leads WHERE has_website = 0"
        ).fetchone()
        generated = conn.execute(
            "SELECT COUNT(*) AS c FROM leads WHERE site_html IS NOT NULL"
        ).fetchone()
        contacted = conn.execute(
            "SELECT COUNT(*) AS c FROM leads WHERE contacted_at IS NOT NULL"
        ).fetchone()
        live = conn.execute(
            q("SELECT COUNT(*) AS c FROM leads WHERE subscription_status = ?"),
            ("active",),
        ).fetchone()
    return {
        "total": _count(total),
        "no_website": _count(no_site),
        "generated": _count(generated),
        "contacted": _count(contacted),
        "live": _count(live),
    }


def _count(row) -> int:
    """Pull the count column out of a heterogeneous row object."""
    if row is None:
        return 0
    if isinstance(row, dict):
        return row.get("c", 0)
    return row[0]
