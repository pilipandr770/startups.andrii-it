"""
FLOW 1 of 2 — PLATFORM SUBSCRIPTION.

Founder pays ANDRII's own Stripe account for their listing and, depending
on tier, the AI pitcher and/or the donation button. This module should be
the ONLY place in the codebase that uses STRIPE_PLATFORM_SECRET_KEY. Do not
import this into anything related to founder donations — see
founder_donation.py for that entirely separate flow.
"""

import stripe
from flask import current_app, url_for

from app.extensions import db
from app.models import Subscription, SubscriptionStatus, SubscriptionTier, SubscriptionPlan


def _configure_stripe():
    stripe.api_key = current_app.config["STRIPE_PLATFORM_SECRET_KEY"]


def create_checkout_session(founder_profile, tier, period="monthly"):
    """Returns a Stripe Checkout Session URL for the platform subscription
    at the given (tier, period). Raises RuntimeError if that combination
    has no Price ID configured yet."""
    if tier not in SubscriptionTier.ALL:
        raise RuntimeError(f"Unknown subscription tier '{tier}'.")
    if period not in SubscriptionPlan.ALL:
        raise RuntimeError(f"Unknown billing period '{period}'.")

    _configure_stripe()

    price_id = current_app.config["STRIPE_PLATFORM_PRICE_IDS"].get((tier, period))
    if not price_id:
        raise RuntimeError(
            f"No Stripe price configured for tier='{tier}', period='{period}'. "
            f"Set STRIPE_PLATFORM_PRICE_ID_{tier.upper()}_{period.upper()} in .env."
        )

    base_url = current_app.config["BASE_URL"]
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}{url_for('payments.subscription_success')}",
        cancel_url=f"{base_url}{url_for('founder.dashboard')}",
        client_reference_id=str(founder_profile.id),
        metadata={
            "founder_profile_id": str(founder_profile.id),
            "tier": tier,
            "period": period,
        },
    )
    return session.url


def handle_webhook_event(event):
    """
    Called only after the caller (routes.py) has verified the Stripe
    signature — never call this with an unverified request body.
    """
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata", {}) or {}
        profile_id = metadata.get("founder_profile_id")
        if profile_id:
            sub = Subscription.query.filter_by(founder_profile_id=int(profile_id)).first()
            if sub:
                sub.status = SubscriptionStatus.ACTIVE
                sub.stripe_customer_id = obj.get("customer")
                sub.stripe_subscription_id = obj.get("subscription")
                if metadata.get("tier") in SubscriptionTier.ALL:
                    sub.tier = metadata["tier"]
                if metadata.get("period") in SubscriptionPlan.ALL:
                    sub.plan = metadata["period"]
                db.session.commit()

    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        status = obj.get("status")
        stripe_sub_id = obj.get("id")
        sub = Subscription.query.filter_by(stripe_subscription_id=stripe_sub_id).first()
        if sub:
            if status == "active":
                sub.status = SubscriptionStatus.ACTIVE
            elif status in ("canceled", "unpaid"):
                sub.status = SubscriptionStatus.CANCELLED
            elif status == "past_due":
                sub.status = SubscriptionStatus.PAST_DUE
            db.session.commit()
