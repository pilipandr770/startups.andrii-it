"""
Tests for the self-reported supporter/donation log. See
app/models/donation.py for why this is self-reported rather than
Stripe-verified — the platform has no API access to a founder's own
Stripe account (see docs/ARCHITECTURE.md, "Two separate Stripe flows").
"""

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, FounderProfile, ProfileStatus, Category,
    Subscription, SubscriptionTier, SubscriptionStatus, Donation,
)


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        db.session.add(Category(slug="other", name_en="Other", name_de="Other"))
        db.session.commit()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_profile(app, tier=SubscriptionTier.PAYMENTS, email="founder@example.com", slug="test-project"):
    with app.app_context():
        user = User(email=email, role=UserRole.FOUNDER)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        profile = FounderProfile(
            user_id=user.id,
            slug=slug,
            project_name="Test Project",
            external_url="https://example.com",
            status=ProfileStatus.PUBLISHED,
        )
        db.session.add(profile)
        db.session.flush()
        db.session.add(Subscription(founder_profile_id=profile.id, tier=tier, status=SubscriptionStatus.ACTIVE))
        db.session.commit()
        return profile.id


def _login(client, email="founder@example.com"):
    client.post("/auth/login", data={"email": email, "password": "password123"})


# --- Model behavior ----------------------------------------------------

def test_totals_and_progress(app):
    profile_id = _make_profile(app)
    with app.app_context():
        db.session.add(Donation(founder_profile_id=profile_id, amount_cents=2000))
        db.session.add(Donation(founder_profile_id=profile_id, amount_cents=3000))
        db.session.commit()

        profile = FounderProfile.query.get(profile_id)
        assert profile.total_raised_cents == 5000
        assert profile.supporter_count == 2
        assert profile.funding_progress_percent is None  # no goal set

        profile.funding_goal_amount_cents = 10000
        db.session.commit()
        assert profile.funding_progress_percent == 50


def test_progress_caps_at_100(app):
    profile_id = _make_profile(app)
    with app.app_context():
        db.session.add(Donation(founder_profile_id=profile_id, amount_cents=20000))
        profile = FounderProfile.query.get(profile_id)
        profile.funding_goal_amount_cents = 10000
        db.session.commit()
        assert profile.funding_progress_percent == 100


# --- Founder-side route: logging and deleting ---------------------------

def test_founder_can_log_a_supporter(app, client):
    _make_profile(app)
    _login(client)

    resp = client.post("/dashboard/supporters", data={
        "amount": "25.00",
        "supporter_name": "Jane",
        "message": "Great work!",
        "donated_on": "2026-09-10",
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        d = Donation.query.first()
        assert d.amount_cents == 2500
        assert d.supporter_name == "Jane"


def test_supporters_page_blocked_below_payments_tier(app, client):
    _make_profile(app, tier=SubscriptionTier.AI_PITCH)
    _login(client)

    resp = client.get("/dashboard/supporters", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Upgrade to the Payments tier" in resp.data


def test_founder_cannot_delete_another_founders_donation(app, client):
    other_profile_id = _make_profile(app, email="other@example.com", slug="other-project")
    with app.app_context():
        db.session.add(Donation(founder_profile_id=other_profile_id, amount_cents=1000))
        db.session.commit()
        donation_id = Donation.query.first().id

    _make_profile(app, email="attacker@example.com", slug="attacker-project")
    _login(client, email="attacker@example.com")

    resp = client.post(f"/dashboard/supporters/{donation_id}/delete")
    assert resp.status_code == 404

    with app.app_context():
        assert Donation.query.get(donation_id) is not None


# --- Public display -------------------------------------------------------

def test_public_page_shows_raised_total_and_disclaimer(app, client):
    profile_id = _make_profile(app)
    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        profile.funding_goal_text = "EUR 1,000 for hosting"
        db.session.add(Donation(founder_profile_id=profile_id, amount_cents=5000, supporter_name="Jane"))
        db.session.commit()

    resp = client.get("/p/test-project")
    assert resp.status_code == 200
    assert b"50.00 EUR" in resp.data
    assert b"not independently verified by the platform" in resp.data
    assert b"Jane" in resp.data


def test_public_page_hides_raised_total_below_payments_tier(app, client):
    profile_id = _make_profile(app, tier=SubscriptionTier.AI_PITCH)
    with app.app_context():
        db.session.add(Donation(founder_profile_id=profile_id, amount_cents=5000))
        db.session.commit()

    resp = client.get("/p/test-project")
    assert resp.status_code == 200
    assert b"raised" not in resp.data
