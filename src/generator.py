"""Claude-powered 1-pager + outreach generator.

Given a business (name, category, address, phone), Claude returns:
  - Site copy (headline, tagline, services, about, hours, CTA)
  - Outreach email pitch
  - Phone-call opener script

The site copy is then rendered into a static HTML 1-pager.
"""
import json
import os
from pathlib import Path

import anthropic

from . import storage
from .slugs import unique_slug


GENERATED_DIR = Path(__file__).parent.parent / "generated_sites"


SITE_COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "Hero headline, 4-8 words, value-forward"},
        "tagline": {"type": "string", "description": "Sub-headline, one sentence"},
        "about": {"type": "string", "description": "2-3 sentence about paragraph"},
        "services": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name", "description"],
                "additionalProperties": False,
            },
            "description": "3-6 services or offerings",
        },
        "why_us": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3 short reasons-to-choose bullets",
        },
        "hours": {"type": "string", "description": "Plausible business hours"},
        "cta": {"type": "string", "description": "Primary call-to-action button text"},
        "color_theme": {
            "type": "string",
            "enum": ["warm", "fresh", "trust", "energetic", "elegant"],
            "description": "Visual mood matching the business type",
        },
    },
    "required": [
        "headline",
        "tagline",
        "about",
        "services",
        "why_us",
        "hours",
        "cta",
        "color_theme",
    ],
    "additionalProperties": False,
}


EMAIL_PITCH_SYSTEM = """You write short, warm, non-spammy cold outreach emails to small business owners.
Tone: friendly neighbor, not marketer. Brief: 4-6 short sentences. No emojis. No hype words.
Always include:
- A specific compliment that proves you actually looked at their business
- One concrete reason a 1-pager website would help them
- A no-pressure offer: "I already built you a free mockup, want to see it?"
- A clear opt-out

Never invent customer reviews or claims you can't verify."""


PHONE_SCRIPT_SYSTEM = """You write 30-second phone-call openers for cold-calling small business owners
to pitch a 1-page website. Tone: respectful, concise, easy to read aloud. Format as plain
dialog the caller speaks; assume the owner picked up. End with a single yes/no ask."""


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic()


def generate_site_copy(lead: dict) -> dict:
    """Use Claude to produce structured copy for the lead's 1-pager."""
    client = _client()
    prompt = f"""Generate compelling 1-page website copy for this small business.

Business: {lead['business_name']}
Category: {lead.get('category') or 'Local business'}
Address: {lead.get('address') or 'Local area'}
Phone: {lead.get('phone') or 'on request'}

Constraints:
- DO NOT invent specific customer reviews, awards, or stats you can't verify.
- DO write copy that feels human, warm, and locally rooted.
- Match the color_theme to the business category's vibe.
- Services should be realistic for this type of business.

Return JSON matching the provided schema."""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={
            "format": {"type": "json_schema", "schema": SITE_COPY_SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def generate_email_pitch(lead: dict, site_url_placeholder: str = "<your-link-here>") -> str:
    """Cold outreach email written by Claude."""
    client = _client()
    prompt = f"""Write a cold email to the owner of:

Business: {lead['business_name']}
Category: {lead.get('category') or 'Local business'}
Location: {lead.get('address') or 'their area'}

Mention that you noticed they don't have a website yet and that you already built
them a free 1-page mockup. The link will be: {site_url_placeholder}

Sign off as: "— Alex"
"""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=EMAIL_PITCH_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in response.content if b.type == "text").strip()


def generate_phone_script(lead: dict) -> str:
    """30-second phone opener written by Claude."""
    client = _client()
    prompt = f"""Write a 30-second cold-call opener for:

Business: {lead['business_name']}
Category: {lead.get('category') or 'Local business'}

The caller is offering a free 1-page website mockup. End with a single yes/no:
'Want me to text you the link?'"""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        system=PHONE_SCRIPT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in response.content if b.type == "text").strip()


# ---- HTML rendering ----------------------------------------------------------

THEME_COLORS = {
    "warm": {"primary": "#c2410c", "accent": "#fed7aa", "bg": "#fffbf5"},
    "fresh": {"primary": "#15803d", "accent": "#bbf7d0", "bg": "#f7fdf9"},
    "trust": {"primary": "#1d4ed8", "accent": "#bfdbfe", "bg": "#f7fafd"},
    "energetic": {"primary": "#be185d", "accent": "#fbcfe8", "bg": "#fefafc"},
    "elegant": {"primary": "#0f172a", "accent": "#cbd5e1", "bg": "#fafafa"},
}


def render_site_html(lead: dict, copy: dict) -> str:
    """Render the 1-pager HTML using the structured copy."""
    theme = THEME_COLORS.get(copy.get("color_theme", "trust"), THEME_COLORS["trust"])

    services_html = "".join(
        f"""
        <div class="service">
          <h3>{s['name']}</h3>
          <p>{s['description']}</p>
        </div>"""
        for s in copy["services"]
    )

    why_html = "".join(f"<li>{w}</li>" for w in copy["why_us"])

    phone = lead.get("phone") or ""
    phone_href = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
    address = lead.get("address") or ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{lead['business_name']} — {copy['tagline']}</title>
<style>
  :root {{
    --primary: {theme['primary']};
    --accent: {theme['accent']};
    --bg: {theme['bg']};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: #1a1a1a;
    line-height: 1.6;
  }}
  header {{
    background: var(--primary);
    color: white;
    padding: 1.25rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }}
  header .brand {{ font-size: 1.4rem; font-weight: 700; }}
  header a {{ color: white; text-decoration: none; font-weight: 500; }}
  .hero {{
    padding: 5rem 2rem;
    text-align: center;
    background: linear-gradient(135deg, var(--accent) 0%, var(--bg) 100%);
  }}
  .hero h1 {{
    font-size: clamp(2rem, 5vw, 3.5rem);
    margin-bottom: 1rem;
    color: var(--primary);
    line-height: 1.15;
  }}
  .hero p {{ font-size: 1.25rem; max-width: 640px; margin: 0 auto 2rem; }}
  .btn {{
    display: inline-block;
    background: var(--primary);
    color: white;
    padding: 0.9rem 2rem;
    border-radius: 999px;
    font-weight: 600;
    text-decoration: none;
    transition: transform 0.15s;
  }}
  .btn:hover {{ transform: translateY(-2px); }}
  section {{ padding: 4rem 2rem; max-width: 1100px; margin: 0 auto; }}
  section h2 {{
    font-size: 2rem;
    margin-bottom: 2rem;
    color: var(--primary);
    text-align: center;
  }}
  .services {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.5rem;
  }}
  .service {{
    background: white;
    padding: 1.75rem;
    border-radius: 12px;
    border: 1px solid var(--accent);
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .service h3 {{ color: var(--primary); margin-bottom: 0.5rem; font-size: 1.15rem; }}
  .about {{ max-width: 720px; margin: 0 auto; text-align: center; font-size: 1.1rem; }}
  .why-us {{ max-width: 540px; margin: 0 auto; }}
  .why-us li {{
    padding: 0.85rem 0 0.85rem 2rem;
    list-style: none;
    position: relative;
    border-bottom: 1px solid var(--accent);
  }}
  .why-us li:before {{
    content: "✓";
    position: absolute;
    left: 0;
    color: var(--primary);
    font-weight: 700;
    font-size: 1.25rem;
  }}
  .contact {{
    background: var(--primary);
    color: white;
    text-align: center;
    padding: 4rem 2rem;
  }}
  .contact h2 {{ color: white; }}
  .contact a {{ color: white; }}
  .contact .info {{
    display: flex;
    justify-content: center;
    gap: 2rem;
    flex-wrap: wrap;
    margin-top: 1rem;
  }}
  footer {{
    padding: 1.5rem;
    text-align: center;
    color: #888;
    font-size: 0.85rem;
  }}
</style>
</head>
<body>

<header>
  <div class="brand">{lead['business_name']}</div>
  <nav><a href="#contact">Contact</a></nav>
</header>

<section class="hero">
  <h1>{copy['headline']}</h1>
  <p>{copy['tagline']}</p>
  <a class="btn" href="#contact">{copy['cta']}</a>
</section>

<section>
  <h2>What we do</h2>
  <div class="services">{services_html}</div>
</section>

<section>
  <h2>About us</h2>
  <p class="about">{copy['about']}</p>
</section>

<section>
  <h2>Why choose us</h2>
  <ul class="why-us">{why_html}</ul>
</section>

<section class="contact" id="contact">
  <h2>{copy['cta']}</h2>
  <p>Hours: {copy['hours']}</p>
  <div class="info">
    {f'<div>📞 <a href="tel:{phone_href}">{phone}</a></div>' if phone else ''}
    {f'<div>📍 {address}</div>' if address else ''}
  </div>
</section>

<footer>
  Mockup generated for {lead['business_name']}. Not yet a live site.
</footer>

</body>
</html>"""


def generate_for_lead(lead_id: int) -> dict:
    """Full pipeline: copy → HTML → email → phone script. Persists to DB."""
    lead = storage.get_lead(lead_id)
    if not lead:
        raise ValueError(f"No lead with id {lead_id}")

    copy = generate_site_copy(lead)
    site_html = render_site_html(lead, copy)
    email_pitch = generate_email_pitch(lead)
    phone_script = generate_phone_script(lead)

    storage.save_generated(
        lead_id, site_html, copy, email_pitch, phone_script, site_kind="single"
    )

    if not lead.get("slug"):
        storage.set_slug(lead_id, unique_slug(lead["business_name"], exclude_lead_id=lead_id))

    GENERATED_DIR.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in lead["business_name"])[:50]
    out_path = GENERATED_DIR / f"{lead_id}_{safe_name}.html"
    out_path.write_text(site_html, encoding="utf-8")

    return {
        "lead_id": lead_id,
        "site_path": str(out_path),
        "copy": copy,
        "email_pitch": email_pitch,
        "phone_script": phone_script,
    }


# ---- Multi-page generation ---------------------------------------------------

MULTIPAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "color_theme": {
            "type": "string",
            "enum": ["warm", "fresh", "trust", "energetic", "elegant"],
        },
        "tagline": {"type": "string", "description": "Site-wide tagline, one sentence"},
        "home": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "subheadline": {"type": "string"},
                "intro": {"type": "string", "description": "1-paragraph welcome on home page"},
                "highlights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "blurb": {"type": "string"},
                        },
                        "required": ["title", "blurb"],
                        "additionalProperties": False,
                    },
                    "description": "3 selling-point highlights",
                },
                "cta": {"type": "string"},
            },
            "required": ["headline", "subheadline", "intro", "highlights", "cta"],
            "additionalProperties": False,
        },
        "services": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "intro": {"type": "string"},
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "details": {"type": "string", "description": "2-3 sentences of detail"},
                        },
                        "required": ["name", "description", "details"],
                        "additionalProperties": False,
                    },
                    "description": "4-6 services with full descriptions",
                },
            },
            "required": ["headline", "intro", "services"],
            "additionalProperties": False,
        },
        "about": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "story": {"type": "string", "description": "2-3 paragraphs about the business"},
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "description"],
                        "additionalProperties": False,
                    },
                    "description": "3 core values",
                },
            },
            "required": ["headline", "story", "values"],
            "additionalProperties": False,
        },
        "contact": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "intro": {"type": "string"},
                "hours": {"type": "string"},
                "service_area": {"type": "string", "description": "e.g. 'Cardiff and surrounding areas'"},
            },
            "required": ["headline", "intro", "hours", "service_area"],
            "additionalProperties": False,
        },
    },
    "required": ["color_theme", "tagline", "home", "services", "about", "contact"],
    "additionalProperties": False,
}


def generate_multipage_copy(lead: dict) -> dict:
    """One Claude call returns structured copy for all 4 pages."""
    client = _client()
    prompt = f"""Generate a complete 4-page website for this small business.

Business: {lead['business_name']}
Category: {lead.get('category') or 'Local business'}
Address: {lead.get('address') or 'Local area'}
Phone: {lead.get('phone') or 'on request'}

The site has these pages: Home, Services, About, Contact.

Constraints:
- DO NOT invent specific customer reviews, awards, or stats you can't verify.
- DO write copy that feels human, warm, and locally rooted.
- Services on the services page should be realistic for this business type.
- About page should feel personal — talk about the owner's craft, the area, why
  they do this work. Avoid generic corporate language.
- Match the color_theme to the business category's vibe.

Return JSON matching the provided schema."""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": MULTIPAGE_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _multipage_shell(lead: dict, copy: dict, current: str, body_html: str) -> str:
    """Wraps a page body with the shared multi-page header/nav/footer/styling."""
    theme = THEME_COLORS.get(copy.get("color_theme", "trust"), THEME_COLORS["trust"])
    phone = lead.get("phone") or ""
    phone_href = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
    pages = [("home", "Home"), ("services", "Services"), ("about", "About"), ("contact", "Contact")]
    nav_html = "".join(
        f'<a href="{"./" if slug == "home" else slug}" '
        f'class="{"active" if slug == current else ""}">{label}</a>'
        for slug, label in pages
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base href="/">
<title>{lead['business_name']} — {copy['tagline']}</title>
<style>
  :root {{
    --primary: {theme['primary']};
    --accent: {theme['accent']};
    --bg: {theme['bg']};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: #1a1a1a;
    line-height: 1.6;
  }}
  header.site-nav {{
    background: var(--primary);
    color: white;
    padding: 1.1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }}
  header.site-nav .brand {{ font-size: 1.3rem; font-weight: 700; }}
  header.site-nav nav {{ display: flex; gap: 1.5rem; flex-wrap: wrap; }}
  header.site-nav nav a {{
    color: white; text-decoration: none; font-weight: 500;
    padding-bottom: 0.25rem;
  }}
  header.site-nav nav a.active {{ border-bottom: 2px solid white; }}
  main {{ min-height: 60vh; }}
  .page-hero {{
    padding: 5rem 2rem 4rem;
    text-align: center;
    background: linear-gradient(135deg, var(--accent) 0%, var(--bg) 100%);
  }}
  .page-hero h1 {{
    font-size: clamp(1.8rem, 4.5vw, 3rem);
    margin-bottom: 1rem;
    color: var(--primary);
    line-height: 1.15;
  }}
  .page-hero p {{ font-size: 1.15rem; max-width: 640px; margin: 0 auto; }}
  .btn {{
    display: inline-block;
    background: var(--primary);
    color: white;
    padding: 0.85rem 2rem;
    border-radius: 999px;
    font-weight: 600;
    text-decoration: none;
    transition: transform 0.15s;
    margin-top: 1.5rem;
  }}
  .btn:hover {{ transform: translateY(-2px); }}
  section {{ padding: 3.5rem 2rem; max-width: 1100px; margin: 0 auto; }}
  section h2 {{
    font-size: 1.75rem;
    margin-bottom: 1.5rem;
    color: var(--primary);
  }}
  .card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.5rem;
  }}
  .card {{
    background: white;
    padding: 1.75rem;
    border-radius: 12px;
    border: 1px solid var(--accent);
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .card h3 {{ color: var(--primary); margin-bottom: 0.5rem; font-size: 1.15rem; }}
  .card p.detail {{ font-size: 0.95rem; color: #475569; margin-top: 0.5rem; }}
  .prose p {{ margin-bottom: 1.2rem; font-size: 1.05rem; }}
  footer {{
    background: var(--primary);
    color: white;
    padding: 2.5rem 2rem;
    text-align: center;
  }}
  footer a {{ color: white; }}
  footer .links {{
    display: flex;
    justify-content: center;
    gap: 2rem;
    flex-wrap: wrap;
    margin: 1rem 0;
    font-size: 0.95rem;
  }}
  footer .links a {{ text-decoration: none; }}
  footer .copy {{ opacity: 0.75; font-size: 0.85rem; margin-top: 0.75rem; }}
</style>
</head>
<body>

<header class="site-nav">
  <a href="/" style="color:white;text-decoration:none;" class="brand">{lead['business_name']}</a>
  <nav>{nav_html}</nav>
</header>

<main>
{body_html}
</main>

<footer>
  <div style="font-weight:600;font-size:1.1rem;">{lead['business_name']}</div>
  <div class="links">
    {f'<a href="tel:{phone_href}">📞 {phone}</a>' if phone else ''}
    <a href="contact">Contact us</a>
  </div>
  <div class="copy">© {lead['business_name']}</div>
</footer>

</body>
</html>"""


def _render_home(lead, copy):
    home = copy["home"]
    highlights = "".join(
        f'<div class="card"><h3>{h["title"]}</h3><p>{h["blurb"]}</p></div>'
        for h in home["highlights"]
    )
    body = f"""
<section class="page-hero">
  <h1>{home['headline']}</h1>
  <p>{home['subheadline']}</p>
  <a class="btn" href="/contact">{home['cta']}</a>
</section>
<section>
  <div class="prose"><p>{home['intro']}</p></div>
</section>
<section>
  <h2>Why us</h2>
  <div class="card-grid">{highlights}</div>
</section>"""
    return _multipage_shell(lead, copy, "home", body)


def _render_services(lead, copy):
    svc = copy["services"]
    items = "".join(
        f"""<div class="card">
          <h3>{s['name']}</h3>
          <p>{s['description']}</p>
          <p class="detail">{s['details']}</p>
        </div>"""
        for s in svc["services"]
    )
    body = f"""
<section class="page-hero">
  <h1>{svc['headline']}</h1>
  <p>{svc['intro']}</p>
</section>
<section>
  <div class="card-grid">{items}</div>
</section>"""
    return _multipage_shell(lead, copy, "services", body)


def _render_about(lead, copy):
    about = copy["about"]
    values = "".join(
        f'<div class="card"><h3>{v["name"]}</h3><p>{v["description"]}</p></div>'
        for v in about["values"]
    )
    paras = "".join(f"<p>{p.strip()}</p>" for p in about["story"].split("\n") if p.strip())
    body = f"""
<section class="page-hero">
  <h1>{about['headline']}</h1>
</section>
<section>
  <div class="prose">{paras}</div>
</section>
<section>
  <h2>What we stand for</h2>
  <div class="card-grid">{values}</div>
</section>"""
    return _multipage_shell(lead, copy, "about", body)


def _render_contact(lead, copy):
    contact = copy["contact"]
    phone = lead.get("phone") or ""
    phone_href = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
    address = lead.get("address") or ""
    info = "".join([
        f'<div class="card"><h3>Phone</h3><p><a href="tel:{phone_href}">{phone}</a></p></div>' if phone else "",
        f'<div class="card"><h3>Address</h3><p>{address}</p></div>' if address else "",
        f'<div class="card"><h3>Hours</h3><p>{contact["hours"]}</p></div>',
        f'<div class="card"><h3>Service area</h3><p>{contact["service_area"]}</p></div>',
    ])
    body = f"""
<section class="page-hero">
  <h1>{contact['headline']}</h1>
  <p>{contact['intro']}</p>
</section>
<section>
  <div class="card-grid">{info}</div>
</section>"""
    return _multipage_shell(lead, copy, "contact", body)


def render_multipage_html(lead: dict, copy: dict) -> dict[str, str]:
    """Return a dict mapping page slug → full HTML."""
    return {
        "home": _render_home(lead, copy),
        "services": _render_services(lead, copy),
        "about": _render_about(lead, copy),
        "contact": _render_contact(lead, copy),
    }


def generate_multipage_for_lead(lead_id: int) -> dict:
    """Multi-page version of the full pipeline."""
    lead = storage.get_lead(lead_id)
    if not lead:
        raise ValueError(f"No lead with id {lead_id}")

    copy = generate_multipage_copy(lead)
    pages = render_multipage_html(lead, copy)
    email_pitch = generate_email_pitch(lead)
    phone_script = generate_phone_script(lead)

    home_html = pages.pop("home")
    storage.save_generated(
        lead_id,
        home_html,
        copy,
        email_pitch,
        phone_script,
        extra_pages=pages,
        site_kind="multi",
    )

    if not lead.get("slug"):
        storage.set_slug(lead_id, unique_slug(lead["business_name"], exclude_lead_id=lead_id))

    return {
        "lead_id": lead_id,
        "copy": copy,
        "page_count": 1 + len(pages),
        "email_pitch": email_pitch,
        "phone_script": phone_script,
    }
