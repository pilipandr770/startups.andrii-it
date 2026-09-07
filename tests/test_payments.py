"""
Tests for the Stripe payment flows: webhook signature verification (Flow 1
— platform subscription) and the anti-scam / tiered-feature guards around
the donation link and AI pitch bot (Flow 2 gating). See
docs/ARCHITECTURE.md, "Two separate Stripe flows" for why these stay
independent, and app/models/subscription.py for the tier model.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, FounderProfile, ProfileStatus, ChatbotConfig,
    Subscription, SubscriptionTier, SubscriptionStatus,
)
from app.founder.forms import stripe_hosted_link


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf_app():
    """A separate app instance with CSRF actually enforced (TestingConfig
    disables it, which is right for form-submission tests but would hide a
    regression of the exact bug these tests guard against — see
    test_webhook_and_chatbot_are_csrf_exempt below)."""
    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _make_published_profile(app, tier, status=SubscriptionStatus.ACTIVE,
                             stripe_link="https://buy.stripe.com/test123", email=None):
    with app.app_context():
        user = User(email=email or f"f_{tier}@example.com", role=UserRole.FOUNDER,
                    legal_entity_name="Test Founder UG")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        profile = FounderProfile(
            user_id=user.id,
            slug=f"proj-{tier}",
            project_name="Proj",
            external_url="https://example.com",
            status=ProfileStatus.PUBLISHED,
            founder_stripe_payment_link=stripe_link,
            funding_goal_text="EUR 1,000",
        )
        db.session.add(profile)
        db.session.flush()

        db.session.add(Subscription(founder_profile_id=profile.id, tier=tier, status=status))
        db.session.add(ChatbotConfig(founder_profile_id=profile.id, is_enabled=True,
                                      pitch_instructions="Answer questions about Proj."))
        db.session.commit()
        return profile.slug


# --- stripe_hosted_link form validator (anti-scam guard) -------------------

@pytest.mark.parametrize("url", [
    "https://buy.stripe.com/abc123",
    "https://donate.stripe.com/abc123",
    "https://stripe.com/somepage",
])
def test_stripe_hosted_link_accepts_stripe_domains(url):
    field = SimpleNamespace(data=url)
    stripe_hosted_link(None, field)  # should not raise


@pytest.mark.parametrize("url", [
    "https://buy.stripe.com.evil.example/abc123",  # suffix-spoof attempt
    "https://evil.example/redirect?to=buy.stripe.com",
    "https://notstripe.com/pay",
    "https://paypal.com/pay",
])
def test_stripe_hosted_link_rejects_non_stripe_domains(url):
    field = SimpleNamespace(data=url)
    with pytest.raises(Exception):
        stripe_hosted_link(None, field)


def test_stripe_hosted_link_allows_empty_field():
    field = SimpleNamespace(data="")
    stripe_hosted_link(None, field)  # optional field — no link is fine


# --- Subscription.has_feature (tier gating) --------------------------------

def test_has_feature_is_cumulative(app):
    with app.app_context():
        sub = Subscription(tier=SubscriptionTier.AI_PITCH, status=SubscriptionStatus.ACTIVE)
        assert sub.has_feature(SubscriptionTier.PRESENTATION) is True
        assert sub.has_feature(SubscriptionTier.AI_PITCH) is True
        assert sub.has_feature(SubscriptionTier.PAYMENTS) is False


def test_has_feature_false_when_subscription_inactive(app):
    with app.app_context():
        sub = Subscription(tier=SubscriptionTier.PAYMENTS, status=SubscriptionStatus.CANCELLED)
        assert sub.has_feature(SubscriptionTier.PRESENTATION) is False


# --- CSRF exemption regression guard ---------------------------------------
# Found via a docker-compose smoke test: with CSRF enforced (as it always is
# outside the test config), both of these public/server-to-server endpoints
# returned "400 The CSRF token is missing" before ever reaching their own
# logic — Stripe's webhook and the anonymous chat widget's fetch() call have
# no CSRF token to send. TestingConfig disables CSRF globally, which would
# silently hide a regression of this exact bug, hence the dedicated fixture.

def test_webhook_is_csrf_exempt(csrf_app, csrf_client):
    assert csrf_app.config["WTF_CSRF_ENABLED"] is True
    csrf_app.config["STRIPE_PLATFORM_WEBHOOK_SECRET"] = ""
    resp = csrf_client.post("/payments/webhook/stripe-platform", data="{}", content_type="application/json")
    assert b"CSRF" not in resp.data
    assert resp.status_code == 500  # reaches our own "secret not configured" guard, not CSRF


def test_chatbot_message_is_csrf_exempt(csrf_app, csrf_client):
    assert csrf_app.config["WTF_CSRF_ENABLED"] is True
    resp = csrf_client.post("/chatbot/nonexistent-slug/message", json={"message": "hi"})
    assert b"CSRF" not in resp.data
    assert resp.status_code == 404  # reaches the route's own slug lookup, not CSRF


# --- Platform subscription webhook: signature verification -----------------

def test_webhook_rejects_when_secret_not_configured(app, client):
    app.config["STRIPE_PLATFORM_WEBHOOK_SECRET"] = ""
    resp = client.post("/payments/webhook/stripe-platform", data="{}", content_type="application/json")
    assert resp.status_code == 500


def test_webhook_rejects_invalid_signature(app, client):
    app.config["STRIPE_PLATFORM_WEBHOOK_SECRET"] = "whsec_test"
    resp = client.post(
        "/payments/webhook/stripe-platform",
        data="{}",
        content_type="application/json",
        headers={"Stripe-Signature": "bogus"},
    )
    assert resp.status_code == 400


def test_webhook_accepts_valid_signature(app, client):
    app.config["STRIPE_PLATFORM_WEBHOOK_SECRET"] = "whsec_test"
    fake_event = {"type": "checkout.session.completed", "data": {"object": {}}}
    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post(
            "/payments/webhook/stripe-platform",
            data="{}",
            content_type="application/json",
            headers={"Stripe-Signature": "valid"},
        )
    assert resp.status_code == 200


# --- Donation link gated by PAYMENTS tier -----------------------------------

def test_donate_redirect_blocked_below_payments_tier(app, client):
    slug = _make_published_profile(app, SubscriptionTier.AI_PITCH)
    resp = client.get(f"/payments/donate/{slug}", follow_redirects=False)
    assert resp.status_code == 302
    assert "buy.stripe.com" not in resp.headers["Location"]


def test_donate_redirect_allowed_at_payments_tier(app, client):
    slug = _make_published_profile(app, SubscriptionTier.PAYMENTS)
    resp = client.get(f"/payments/donate/{slug}", follow_redirects=False)
    assert resp.status_code == 302
    assert "buy.stripe.com" in resp.headers["Location"]


def test_donate_redirect_blocked_when_subscription_inactive(app, client):
    slug = _make_published_profile(app, SubscriptionTier.PAYMENTS, status=SubscriptionStatus.CANCELLED)
    resp = client.get(f"/payments/donate/{slug}", follow_redirects=False)
    assert resp.status_code == 302
    assert "buy.stripe.com" not in resp.headers["Location"]


# --- AI pitch bot gated by AI_PITCH tier ------------------------------------

def test_chatbot_blocked_below_ai_pitch_tier(app, client):
    slug = _make_published_profile(app, SubscriptionTier.PRESENTATION)
    resp = client.post(f"/chatbot/{slug}/message", json={"message": "hi"})
    assert resp.status_code == 200
    assert "unlocked" in resp.get_json()["reply"]


def test_chatbot_allowed_at_ai_pitch_tier(app, client):
    slug = _make_published_profile(app, SubscriptionTier.AI_PITCH)
    resp = client.post(f"/chatbot/{slug}/message", json={"message": "hi"})
    assert resp.status_code == 200
    assert "unlocked" not in resp.get_json()["reply"]
