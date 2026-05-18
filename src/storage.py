"""SQLite-backed lead storage."""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "leads.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    created_at TEXT,
    contacted_at TEXT,
    UNIQUE(business_name, address)
);

CREATE INDEX IF NOT EXISTS idx_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_has_website ON leads(has_website);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def add_lead(lead: dict) -> int | None:
    """Insert a lead. Returns row id, or None if duplicate."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO leads (business_name, category, address, phone, email,
                                   has_website, google_maps_url, source, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                """,
                (
                    lead["business_name"],
                    lead.get("category"),
                    lead.get("address"),
                    lead.get("phone"),
                    lead.get("email"),
                    1 if lead.get("has_website") else 0,
                    lead.get("google_maps_url"),
                    lead.get("source", "manual"),
                    datetime.utcnow().isoformat(),
                ),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def list_leads(only_no_website: bool = True, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM leads WHERE 1=1"
    args: list = []
    if only_no_website:
        q += " AND has_website = 0"
    if status:
        q += " AND status = ?"
        args.append(status)
    q += " ORDER BY created_at DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def get_lead(lead_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None


def update_lead(lead_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    args = list(fields.values()) + [lead_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", args)


def mark_contacted(lead_id: int, status: str = "contacted") -> None:
    update_lead(lead_id, status=status, contacted_at=datetime.utcnow().isoformat())


def save_generated(lead_id: int, site_html: str, site_copy: dict, email_pitch: str, phone_script: str) -> None:
    update_lead(
        lead_id,
        site_html=site_html,
        site_copy_json=json.dumps(site_copy),
        email_pitch=email_pitch,
        phone_script=phone_script,
    )


def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        no_site = conn.execute("SELECT COUNT(*) FROM leads WHERE has_website = 0").fetchone()[0]
        generated = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE site_html IS NOT NULL"
        ).fetchone()[0]
        contacted = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE contacted_at IS NOT NULL"
        ).fetchone()[0]
    return {"total": total, "no_website": no_site, "generated": generated, "contacted": contacted}
