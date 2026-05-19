"""Flask dashboard for browsing leads and pitching them.

Run:
    python app.py
Then open http://localhost:5000
"""
import os

from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, url_for, jsonify, Response

load_dotenv()

from src import finder, generator, storage

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")


@app.route("/")
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
    )


@app.route("/lead/<int:lead_id>")
def lead_detail(lead_id):
    lead = storage.get_lead(lead_id)
    if not lead:
        abort(404)
    return render_template("lead_detail.html", lead=lead)


@app.route("/lead/<int:lead_id>/generate", methods=["POST"])
def lead_generate(lead_id):
    try:
        generator.generate_for_lead(lead_id)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.route("/lead/<int:lead_id>/preview")
def lead_preview(lead_id):
    lead = storage.get_lead(lead_id)
    if not lead or not lead.get("site_html"):
        abort(404)
    return Response(lead["site_html"], mimetype="text/html")


@app.route("/lead/<int:lead_id>/mark", methods=["POST"])
def lead_mark(lead_id):
    status = request.form.get("status", "contacted")
    storage.mark_contacted(lead_id, status=status)
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.route("/search", methods=["POST"])
def search():
    """Trigger a Google Places search (requires GOOGLE_PLACES_API_KEY)."""
    query = request.form.get("query", "").strip()
    if not query:
        return redirect(url_for("dashboard"))
    try:
        finder.search_google_places(query, max_results=20)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    storage.init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
