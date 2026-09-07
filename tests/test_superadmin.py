"""
Tests for the superadmin panel's expanded controls: publishing a project
directly (skipping the moderation queue) and setting/revoking a manually
granted subscription tier — used for Andrii's own projects, which publish
and unlock features without ever going through Stripe.
"""

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, FounderProfile, ProfileStatus,
    Subscription, SubscriptionTier, SubscriptionStatus,
)


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


def _make_profile(app, status=ProfileStatus.DRAFT):
    with app.app_context():
        owner = User(email="super@example.com", role=UserRole.SUPERADMIN)
        owner.set_password("password123")
        db.session.add(owner)

        founder = User(email="founder@example.com", role=UserRole.FOUNDER)
        founder.set_password("password123")
        db.session.add(founder)
        db.session.commit()

        profile = FounderProfile(
            user_id=founder.id,
            slug="own-project",
            project_name="Own Project",
            external_url="https://example.com",
            status=status,
        )
        db.session.add(profile)
        db.session.commit()
        return profile.id


def _login_superadmin(client):
    client.post("/auth/login", data={"email": "super@example.com", "password": "password123"})


def test_publish_skips_moderation_queue(app, client):
    profile_id = _make_profile(app, status=ProfileStatus.DRAFT)
    _login_superadmin(client)

    resp = client.post(f"/superadmin/profile/{profile_id}/publish", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        assert profile.status == ProfileStatus.PUBLISHED
        assert profile.published_at is not None


def test_grant_subscription_sets_chosen_tier(app, client):
    profile_id = _make_profile(app)
    _login_superadmin(client)

    resp = client.post(
        f"/superadmin/subscription/{profile_id}/grant",
        data={"tier": SubscriptionTier.AI_PITCH},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        sub = FounderProfile.query.get(profile_id).subscription
        assert sub.tier == SubscriptionTier.AI_PITCH
        assert sub.status == SubscriptionStatus.ACTIVE


def test_grant_subscription_rejects_unknown_tier(app, client):
    profile_id = _make_profile(app)
    _login_superadmin(client)

    resp = client.post(
        f"/superadmin/subscription/{profile_id}/grant",
        data={"tier": "not-a-real-tier"},
    )
    assert resp.status_code == 400


def test_revoke_subscription_cancels_it(app, client):
    profile_id = _make_profile(app)
    with app.app_context():
        db.session.add(Subscription(
            founder_profile_id=profile_id,
            tier=SubscriptionTier.PAYMENTS,
            status=SubscriptionStatus.ACTIVE,
        ))
        db.session.commit()

    _login_superadmin(client)
    resp = client.post(f"/superadmin/subscription/{profile_id}/revoke", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        sub = FounderProfile.query.get(profile_id).subscription
        assert sub.status == SubscriptionStatus.CANCELLED
        assert sub.has_feature(SubscriptionTier.PRESENTATION) is False


def test_superadmin_routes_redirect_when_not_logged_in(app, client):
    profile_id = _make_profile(app)
    resp = client.post(f"/superadmin/profile/{profile_id}/publish")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_superadmin_routes_reject_plain_founder(app, client):
    profile_id = _make_profile(app)
    client.post("/auth/login", data={"email": "founder@example.com", "password": "password123"})
    resp = client.post(f"/superadmin/profile/{profile_id}/publish")
    assert resp.status_code == 403
