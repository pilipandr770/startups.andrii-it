"""
Tests that the admin approve flow re-checks a listing's link reputation
right before publishing and refuses to auto-publish a flagged link — see
app/admin/routes.py::approve and app/compliance/url_reputation.py. This
protects marketplace VISITORS, not the founder (contrast with
tests/test_moderation.py, which covers the substantive-edit reset rule).
"""

from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db
from app.models import User, UserRole, FounderProfile, ProfileStatus

# admin/routes.py and founder/routes.py both do
# `from app.compliance.url_reputation import check_url_reputation`, which
# binds a local name in each module — patching the source module's
# attribute wouldn't affect those already-bound references, so we patch
# each call site directly.
ADMIN_CHECK = "app.admin.routes.check_url_reputation"
FOUNDER_CHECK = "app.founder.routes.check_url_reputation"


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


def _make_profile(app):
    with app.app_context():
        admin = User(email="admin@example.com", role=UserRole.ADMIN)
        admin.set_password("password123")
        db.session.add(admin)

        founder = User(email="founder@example.com", role=UserRole.FOUNDER)
        founder.set_password("password123")
        db.session.add(founder)
        db.session.commit()

        profile = FounderProfile(
            user_id=founder.id, slug="test-project", project_name="Test Project",
            external_url="https://example.com", status=ProfileStatus.PENDING_REVIEW,
        )
        db.session.add(profile)
        db.session.commit()
        return profile.id


def _login_admin(client):
    client.post("/auth/login", data={"email": "admin@example.com", "password": "password123"})


def test_approve_blocked_when_link_flagged(app, client):
    profile_id = _make_profile(app)
    _login_admin(client)

    with patch(ADMIN_CHECK, return_value=("flagged", "URLhaus: currently listed")):
        resp = client.post(f"/admin/profile/{profile_id}/approve", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Not approved" in resp.data

    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        assert profile.status == ProfileStatus.PENDING_REVIEW
        assert profile.url_reputation_status == "flagged"


def test_approve_anyway_overrides_flag(app, client):
    profile_id = _make_profile(app)
    _login_admin(client)

    with patch(ADMIN_CHECK, return_value=("flagged", "URLhaus: currently listed")):
        resp = client.post(
            f"/admin/profile/{profile_id}/approve",
            data={"override_reputation_warning": "1"},
            follow_redirects=True,
        )
    assert resp.status_code == 200

    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        assert profile.status == ProfileStatus.PUBLISHED


def test_approve_proceeds_normally_when_clean(app, client):
    profile_id = _make_profile(app)
    _login_admin(client)

    with patch(ADMIN_CHECK, return_value=("clean", "No threats found.")):
        resp = client.post(f"/admin/profile/{profile_id}/approve", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Approved" in resp.data

    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        assert profile.status == ProfileStatus.PUBLISHED
        assert profile.url_reputation_status == "clean"


def test_approve_proceeds_when_lookup_fails(app, client):
    """A reputation-check outage must never block legitimate moderation."""
    profile_id = _make_profile(app)
    _login_admin(client)

    with patch(ADMIN_CHECK, side_effect=Exception("network down")):
        resp = client.post(f"/admin/profile/{profile_id}/approve", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        assert profile.status == ProfileStatus.PUBLISHED


def test_recheck_link_route_updates_stored_result(app, client):
    profile_id = _make_profile(app)
    _login_admin(client)

    with patch(ADMIN_CHECK, return_value=("flagged", "VirusTotal: 2 engines flagged malicious")):
        resp = client.post(f"/admin/profile/{profile_id}/recheck-link", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = FounderProfile.query.get(profile_id)
        assert profile.url_reputation_status == "flagged"
        assert profile.url_reputation_checked_at is not None


def test_submit_for_review_records_initial_reputation_check(app, client):
    with app.app_context():
        founder = User(email="founder2@example.com", role=UserRole.FOUNDER)
        founder.set_password("password123")
        db.session.add(founder)
        db.session.commit()
        profile = FounderProfile(
            user_id=founder.id, slug="new-project", project_name="New Project",
            external_url="https://example.com", status=ProfileStatus.DRAFT,
        )
        db.session.add(profile)
        db.session.commit()

    client.post("/auth/login", data={"email": "founder2@example.com", "password": "password123"})

    with patch(FOUNDER_CHECK, return_value=("clean", "No threats found.")):
        client.post("/dashboard/profile/submit", follow_redirects=True)

    with app.app_context():
        profile = FounderProfile.query.filter_by(slug="new-project").first()
        assert profile.status == ProfileStatus.PENDING_REVIEW
        assert profile.url_reputation_status == "clean"
