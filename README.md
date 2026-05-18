# Website Creator

Find local businesses without a website, auto-generate a 1-page mockup for each, and draft a cold-pitch email + phone script — all in one workflow.

## What it does

1. **Find leads** — pull business listings from Google Places (or use bundled samples) and filter to ones with no `website` field.
2. **Generate a 1-pager** — Claude writes the copy (headline, services, about, why-us, hours, CTA) and the app renders a polished, mobile-friendly HTML site.
3. **Draft outreach** — Claude writes a short, non-spammy email and a 30-second phone opener tailored to the business.
4. **Track status** — mark leads as contacted / interested / closed in a small dashboard.

## Quick start (no API keys required)

```bash
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>. The app auto-loads bundled sample leads so you can click around immediately.

To generate sites and pitches with real AI output, set `ANTHROPIC_API_KEY` in a `.env` file (copy from `.env.example`).

## Real lead sourcing (optional)

To pull live businesses instead of the samples:

1. Get a Google Places API key from <https://console.cloud.google.com>.
2. Set `GOOGLE_PLACES_API_KEY` in `.env`.
3. Either:
   - In the dashboard, type a query like `plumber in Austin, TX` and hit **Search Google Places**.
   - Or from the CLI: `python run.py search "bakery in Charleston SC"`.

The finder calls Places Details on each result and filters to those with no `website` field.

## CLI

```bash
python run.py seed                       # load sample leads
python run.py search "plumber Austin"    # real search (needs Places API key)
python run.py list                       # list leads
python run.py generate 3                 # generate site + pitches for lead id 3
python run.py generate-all               # generate for every lead missing one
```

## Stack

- Python 3.10+
- Flask (dashboard)
- SQLite (lead storage — `leads.db`)
- Anthropic Claude Opus 4.7 (copy + email + phone-script generation, adaptive thinking on)
- Google Places API (optional, for live lead sourcing)

Generated HTML 1-pagers also land in `./generated_sites/` so you can host them anywhere or send a static link.

## Legal & deliverability notes

This tool is a **lead-research and content-drafting** aid. **You** are responsible for the outreach that follows. Before you send a single email or place a single call, please confirm you're compliant with:

- **CAN-SPAM (US email)** — include a real postal address, a working unsubscribe link, and accurate sender info. Don't disguise the commercial nature of the email.
- **GDPR / ePrivacy (EU & UK)** — a B2B cold email to an individual at a small business is usually personal data. You need a lawful basis (legitimate interest is the most common), a clear opt-out, and a privacy notice on first contact.
- **TCPA (US calls/SMS)** — don't text without prior express consent. Don't auto-dial. Respect the federal Do-Not-Call registry.
- **State laws** — California, Virginia, and others have stricter rules; check your jurisdiction.
- **Google ToS** — if you're sourcing from Google Places, use the official API as this tool does. Don't scrape.

The default email template Claude writes is intentionally short, warm, and includes an opt-out — but you still need to add your own postal address before sending.

## What's intentionally simple

This is an MVP. Things you'd want to add for production:

- Email deliverability: SPF/DKIM, warmed-up sending domain, replies threading
- Hosting flow: actually deploying generated sites to a real domain on conversion
- CRM sync: HubSpot / Pipedrive integration
- Lead enrichment: pulling emails from public sources (Hunter, Apollo, etc.)
- Multi-user auth and per-rep pipelines
