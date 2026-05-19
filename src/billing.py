"""Stripe Checkout + webhook integration.

Plans are configured via env vars holding Stripe Price IDs. The app
gracefully degrades if Stripe isn't configured — billing routes will
return a helpful error instead of crashing.
"""
import os
from typing import Optional

try:
    import stripe
except ImportError:
    stripe = None

from . import storage


PLANS = {
    "basic": {
        "label": "Basic one-pager",
        "price_env": "STRIPE_PRICE_ID_BASIC",
        "monthly_gbp": 19,
    },
    "custom_domain": {
        "label": "One-pager + custom domain",
        "price_env": "STRIPE_PRICE_ID_CUSTOM_DOMAIN",
        "monthly_gbp": 29,
    },
    "multipage": {
        "label": "Multi-page site",
        "price_env": "STRIPE_PRICE_ID_MULTIPAGE",
        "monthly_gbp": 49,
    },
    "premium": {
        "label": "Multi-page + monthly updates",
        "price_env": "STRIPE_PRICE_ID_PREMIUM",
        "monthly_gbp": 79,
    },
}


def _require_stripe():
    if stripe is None:
        raise RuntimeError("stripe library not installed. Run: pip install stripe")
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not set in environment")
    stripe.api_key = key
    return stripe


def price_id_for(plan: str) -> Optional[str]:
    info = PLANS.get(plan)
    if not info:
        return None
    return os.environ.get(info["price_env"])


def create_checkout_session(lead: dict, plan: str, base_url: str) -> str:
    """Create a Stripe Checkout session and return its URL."""
    s = _require_stripe()
    price = price_id_for(plan)
    if not price:
        raise RuntimeError(
            f"No Stripe price ID configured for plan '{plan}'. "
            f"Set {PLANS[plan]['price_env']} in env."
        )

    session = s.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=f"{base_url}/billing/return?session_id={{CHECKOUT_SESSION_ID}}&lead_id={lead['id']}",
        cancel_url=f"{base_url}/lead/{lead['id']}",
        customer_email=lead.get("email") or None,
        client_reference_id=str(lead["id"]),
        metadata={"lead_id": str(lead["id"]), "plan": plan},
        subscription_data={"metadata": {"lead_id": str(lead["id"]), "plan": plan}},
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> None:
    """Verify and dispatch a Stripe webhook event."""
    s = _require_stripe()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET not set in environment")

    event = s.Webhook.construct_event(payload, sig_header, secret)
    typ = event["type"]
    obj = event["data"]["object"]

    if typ == "checkout.session.completed":
        lead_id = _lead_id_from(obj)
        plan = (obj.get("metadata") or {}).get("plan", "basic")
        if lead_id:
            storage.update_lead(
                lead_id,
                subscription_status="active",
                plan=plan,
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("subscription"),
            )

    elif typ in ("customer.subscription.updated", "customer.subscription.created"):
        lead_id = _lead_id_from(obj)
        status = obj.get("status", "inactive")
        if lead_id:
            storage.update_lead(lead_id, subscription_status=status)

    elif typ == "customer.subscription.deleted":
        lead_id = _lead_id_from(obj)
        if lead_id:
            storage.update_lead(lead_id, subscription_status="canceled")

    elif typ == "invoice.payment_failed":
        lead_id = _lead_id_from(obj)
        if lead_id:
            storage.update_lead(lead_id, subscription_status="past_due")


def _lead_id_from(obj: dict) -> Optional[int]:
    """Extract lead_id from metadata or client_reference_id."""
    md = obj.get("metadata") or {}
    if md.get("lead_id"):
        return int(md["lead_id"])
    if obj.get("client_reference_id"):
        return int(obj["client_reference_id"])
    sub_md = (obj.get("subscription_details") or {}).get("metadata") or {}
    if sub_md.get("lead_id"):
        return int(sub_md["lead_id"])
    return None
