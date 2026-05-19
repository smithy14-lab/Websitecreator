# Website Creator

Find local businesses without a website, auto-generate a 1-page mockup for each, draft a cold-pitch email + phone script, then sell the generated site as a hosted monthly subscription via Stripe.

## What it does

1. **Find leads** — pull business listings from Google Places (New API) and filter to ones with no website.
2. **Generate a 1-pager** — Claude writes the copy and the app renders a polished, mobile-friendly HTML site.
3. **Draft outreach** — Claude writes a short, non-spammy email and a 30-second phone opener.
4. **Host & monetize** — every generated site has a public URL (`/s/business-slug`). Send it to the prospect; they subscribe through Stripe Checkout; their site goes live.
5. **Track status** — mark leads as contacted / interested / closed in the dashboard.

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY, ADMIN_PASSWORD, etc.
python app.py
```

Open <http://localhost:5000>. Sign in with the `ADMIN_PASSWORD` you set. Local dev uses a SQLite file (`leads.db`).

## Production deployment (Railway)

1. Push this repo to GitHub.
2. Create a new project at <https://railway.app>, "Deploy from GitHub", pick this repo.
3. In the project, click **+ New → Database → PostgreSQL**. Railway auto-injects `DATABASE_URL`.
4. Set the rest of the env vars in the service's **Variables** tab — see `.env.example` for the full list.
5. Add a custom domain in Railway's **Settings → Networking**, point your DNS at it, set `BASE_URL=https://yourdomain.com`.
6. Configure the Stripe webhook (next section).

### Stripe setup

1. Create products + recurring prices in <https://dashboard.stripe.com/products>:
   - Basic one-pager — £19/month
   - Custom-domain upgrade — £29/month
   - Multi-page — £49/month
   - Premium (multi-page + updates) — £79/month
2. Copy each `price_xxx` ID into the matching `STRIPE_PRICE_ID_*` env var.
3. Add a webhook endpoint at <https://dashboard.stripe.com/webhooks>:
   - URL: `https://yourdomain.com/billing/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`
   - Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.

## CLI

```bash
python run.py search "plumber Austin"    # add leads via Google Places
python run.py list                       # list leads
python run.py generate 3                 # generate site + pitches for lead id 3
python run.py generate-all               # generate for every lead missing one
```

## Stack

- Python 3.12+
- Flask, gunicorn
- SQLite (dev) / Postgres (prod) — selected automatically via `DATABASE_URL`
- Anthropic Claude Opus 4.7 — copy + outreach
- Google Places API (New) — lead sourcing
- Stripe Checkout + webhooks — subscription billing

## Legal & deliverability notes

This tool is a **lead-research and content-drafting** aid. **You** are responsible for the outreach that follows. Before you send a single email or place a single call, please confirm you're compliant with:

- **CAN-SPAM (US email)** — include a real postal address, a working unsubscribe link, accurate sender info.
- **GDPR / ePrivacy (EU & UK)** — B2B cold email is usually personal data. You need a lawful basis (legitimate interest is the most common), a clear opt-out, and a privacy notice on first contact.
- **TCPA (US calls/SMS)** — don't auto-dial. Respect the federal Do-Not-Call registry.
- **Google ToS** — use the official Places API as this tool does. Don't scrape.

The default email template Claude writes is intentionally short, warm, and includes an opt-out — but you still need to add your own postal address before sending.
