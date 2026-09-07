import stripe
from flask import redirect, url_for, flash, request, jsonify, abort, current_app
from flask_login import login_required, current_user

from app.payments import bp
from app.payments.platform_subscription import create_checkout_session, handle_webhook_event
from app.payments.founder_donation import get_donation_redirect_url
from app.models import FounderProfile, ProfileStatus, SubscriptionTier, SubscriptionPlan
from app.extensions import csrf


# --- Flow 1: platform subscription (founder -> Andrii) ---

@bp.route("/subscribe/<tier>/<period>")
@login_required
def subscribe(tier, period):
    profile = current_user.founder_profile
    if not profile:
        flash("Create your project profile first.", "warning")
        return redirect(url_for("founder.edit_profile"))

    if tier not in SubscriptionTier.ALL or period not in SubscriptionPlan.ALL:
        abort(404)

    try:
        checkout_url = create_checkout_session(profile, tier=tier, period=period)
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("founder.dashboard"))

    return redirect(checkout_url)


@bp.route("/subscription/success")
@login_required
def subscription_success():
    flash("Subscription active. Thank you!", "success")
    return redirect(url_for("founder.dashboard"))


@bp.route("/webhook/stripe-platform", methods=["POST"])
@csrf.exempt
def stripe_platform_webhook():
    """
    Webhook for the PLATFORM subscription Stripe account only. Every event
    is signature-verified against STRIPE_PLATFORM_WEBHOOK_SECRET before its
    body is trusted — an unverified POST here could otherwise be used to
    fake "subscription active" and unlock paid features for free.

    Exempt from CSRF: this is a server-to-server call from Stripe, not a
    browser session, so it can never carry (or need) a CSRF token — the
    Stripe signature check above is the actual authentication here.
    """
    webhook_secret = current_app.config["STRIPE_PLATFORM_WEBHOOK_SECRET"]
    if not webhook_secret:
        current_app.logger.error(
            "Stripe platform webhook called but STRIPE_PLATFORM_WEBHOOK_SECRET "
            "is not configured — refusing to process unverified events."
        )
        abort(500)

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        abort(400)  # malformed payload
    except stripe.error.SignatureVerificationError:
        abort(400)  # signature didn't match — not really from Stripe

    handle_webhook_event(event)
    return jsonify({"received": True})


# --- Flow 2: founder donations (visitor -> founder, platform never touches funds) ---

@bp.route("/donate/<slug>")
def donate_redirect(slug):
    profile = FounderProfile.query.filter_by(slug=slug).first_or_404()
    if profile.status != ProfileStatus.PUBLISHED:
        abort(404)

    if not (profile.subscription and profile.subscription.has_feature(SubscriptionTier.PAYMENTS)):
        flash("This project hasn't unlocked payment acceptance yet.", "info")
        return redirect(url_for("marketplace.project_detail", slug=slug))

    url = get_donation_redirect_url(profile)
    if not url:
        flash("This project hasn't set up a donation link yet.", "info")
        return redirect(url_for("marketplace.project_detail", slug=slug))

    return redirect(url)
