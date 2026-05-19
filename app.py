"""Flask app: admin dashboard, public site hosting, Stripe billing."""
import functools
import os
import secrets

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    Response,
    session,
    url_for,
)

load_dotenv()

from src import billing, finder, generator, storage

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# Subdomain hosting: when SUBDOMAIN_MODE=1 + APEX_DOMAIN set, requests to
# <slug>.<apex> serve the customer's site directly.
SUBDOMAIN_MODE = os.environ.get("SUBDOMAIN_MODE") == "1"
APEX_DOMAIN = os.environ.get("APEX_DOMAIN", "").lower().lstrip(".")
RESERVED_SUBDOMAINS = {"www", "app", "admin", "api", "dashboard", "billing", "mail"}


# ---- Auth -------------------------------------------------------------------

def require_admin(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD:
        return (
            "ADMIN_PASSWORD env var not set. Add it to .env (local) "
            "or your hosting platform's secrets (production).",
            500,
        )
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            session.permanent = True
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        flash("Wrong password.")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---- Admin dashboard --------------------------------------------------------

@app.route("/")
@require_admin
def dashboard():
    status_filter = request.args.get("status")
    only_no_website = request.args.get("only_no_website", "1") == "1"
    leads = storage.list_leads(only_no_website=only_no_website, status=status_filter)
    return render_template(
        "dashboard.html",
        leads=leads,
        stats=storage.stats(),
        status_filter=status_filter,
        only_no_website=only_no_website,
        base_url=BASE_URL,
    )


@app.route("/lead/<int:lead_id>")
@require_admin
def lead_detail(lead_id):
    lead = storage.get_lead(lead_id)
    if not lead:
        abort(404)
    return render_template(
        "lead_detail.html",
        lead=lead,
        base_url=BASE_URL,
        plans=billing.PLANS,
    )


@app.route("/lead/<int:lead_id>/generate", methods=["POST"])
@require_admin
def lead_generate(lead_id):
    try:
        generator.generate_for_lead(lead_id)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.route("/lead/<int:lead_id>/preview")
@require_admin
def lead_preview(lead_id):
    """Admin-only raw preview without the public preview banner."""
    lead = storage.get_lead(lead_id)
    if not lead or not lead.get("site_html"):
        abort(404)
    return Response(lead["site_html"], mimetype="text/html")


@app.route("/lead/<int:lead_id>/mark", methods=["POST"])
@require_admin
def lead_mark(lead_id):
    status = request.form.get("status", "contacted")
    storage.mark_contacted(lead_id, status=status)
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.route("/search", methods=["POST"])
@require_admin
def search():
    query = request.form.get("query", "").strip()
    if not query:
        return redirect(url_for("dashboard"))
    try:
        finder.search_google_places(query, max_results=20)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    return redirect(url_for("dashboard"))


# ---- Public site hosting ----------------------------------------------------

PREVIEW_BANNER = """
<div style="position:fixed;bottom:0;left:0;right:0;background:#0f172a;color:#fff;
            padding:0.85rem 1.25rem;font:14px/1.4 -apple-system,system-ui,sans-serif;
            text-align:center;z-index:9999;box-shadow:0 -2px 12px rgba(0,0,0,0.2);">
  Preview website built for you.
  <a href="{subscribe_url}" style="color:#fff;text-decoration:underline;font-weight:600;
     margin-left:0.5rem;">
    Claim this site →
  </a>
</div>
"""

PAST_DUE_BANNER = """
<div style="background:#dc2626;color:#fff;
            padding:0.7rem 1.25rem;font:14px/1.4 -apple-system,system-ui,sans-serif;
            text-align:center;position:sticky;top:0;z-index:9999;">
  Payment failed — your site will go offline soon. Update your card.
</div>
"""


def _detect_site_subdomain() -> str | None:
    """Return the customer-site subdomain, or None if request is for the admin."""
    if not (SUBDOMAIN_MODE and APEX_DOMAIN):
        return None
    host = request.host.lower().split(":")[0]
    if host in (APEX_DOMAIN, f"www.{APEX_DOMAIN}"):
        return None
    if not host.endswith(f".{APEX_DOMAIN}"):
        return None
    sub = host[: -len(f".{APEX_DOMAIN}")]
    if not sub or "." in sub or sub in RESERVED_SUBDOMAINS:
        return None
    return sub


@app.before_request
def serve_subdomain_site():
    """If the request targets <slug>.<apex>, serve the customer site directly."""
    sub = _detect_site_subdomain()
    if not sub:
        return None
    lead = storage.get_lead_by_slug(sub)
    if not lead or not lead.get("site_html"):
        abort(404)
    return _render_public_site(lead)


def _render_public_site(lead: dict) -> Response:
    """Render a lead's site, swapping in a banner based on subscription state."""
    status = lead.get("subscription_status") or "inactive"

    if status == "canceled":
        return Response(
            render_template("site_canceled.html", lead=lead, base_url=BASE_URL),
            status=410,
            mimetype="text/html",
        )

    html = lead["site_html"]
    no_banner = request.args.get("noBanner") == "1"

    if not no_banner:
        if status == "inactive":
            banner = PREVIEW_BANNER.format(
                subscribe_url=f"{BASE_URL}/claim/{lead['slug']}"
            )
            html = html.replace("</body>", f"{banner}</body>")
        elif status == "past_due":
            html = html.replace("<body>", f"<body>{PAST_DUE_BANNER}", 1)

    return Response(html, mimetype="text/html")


@app.route("/s/<slug>")
def public_site(slug):
    lead = storage.get_lead_by_slug(slug)
    if not lead or not lead.get("site_html"):
        abort(404)
    return _render_public_site(lead)


@app.route("/claim/<slug>")
def claim(slug):
    """Public landing page for a prospect to subscribe to their generated site."""
    lead = storage.get_lead_by_slug(slug)
    if not lead or not lead.get("site_html"):
        abort(404)
    if lead.get("subscription_status") == "active":
        return redirect(f"{BASE_URL}/s/{slug}")
    return render_template(
        "claim.html",
        lead=lead,
        slug=slug,
        plans=billing.PLANS,
        base_url=BASE_URL,
    )


# ---- Billing ----------------------------------------------------------------

@app.route("/billing/subscribe/<int:lead_id>", methods=["POST"])
def billing_subscribe(lead_id):
    """Create a Stripe Checkout session and redirect."""
    lead = storage.get_lead(lead_id)
    if not lead:
        abort(404)
    plan = request.form.get("plan", "basic")
    if plan not in billing.PLANS:
        return jsonify({"error": f"Unknown plan: {plan}"}), 400
    try:
        url = billing.create_checkout_session(lead, plan, BASE_URL)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    return redirect(url, code=303)


@app.route("/billing/return")
def billing_return():
    """Stripe redirects here after successful checkout."""
    lead_id = request.args.get("lead_id")
    if lead_id:
        lead = storage.get_lead(int(lead_id))
        if lead and lead.get("slug"):
            return redirect(f"{BASE_URL}/s/{lead['slug']}")
    return redirect(url_for("dashboard"))


@app.route("/billing/webhook", methods=["POST"])
def billing_webhook():
    sig = request.headers.get("Stripe-Signature", "")
    try:
        billing.handle_webhook(request.data, sig)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return "", 200


# ---- Startup ----------------------------------------------------------------

storage.init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
