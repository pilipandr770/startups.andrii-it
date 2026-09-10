"""
Tests for self-service and superadmin account/project deletion, and
password changes. See app/models/user.py and app/models/founder_profile.py
for the cascade relationships this relies on (deleting a User or
FounderProfile must clean up everything hanging off it).
"""

import os

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, FounderProfile, ProfileStatus,
    ChatbotConfig, Subscription, Donation,
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


def _make_founder_with_profile(app, email="founder@example.com", password="password123"):
    with app.app_context():
        user = User(email=email, role=UserRole.FOUNDER)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        profile = FounderProfile(
            user_id=user.id, slug="test-project", project_name="Test Project",
            external_url="https://example.com", status=ProfileStatus.PUBLISHED,
        )
        db.session.add(profile)
        db.session.flush()
        db.session.add(ChatbotConfig(founder_profile_id=profile.id, pitch_instructions="hi"))
        db.session.add(Subscription(founder_profile_id=profile.id))
        db.session.add(Donation(founder_profile_id=profile.id, amount_cents=1000))
        db.session.commit()
        return user.id, profile.id


def _login(client, email, password="password123"):
    return client.post("/auth/login", data={"email": email, "password": password})


# --- Change password -------------------------------------------------------

def test_change_password_succeeds_with_correct_current_password(app, client):
    user_id, _ = _make_founder_with_profile(app)
    _login(client, "founder@example.com")

    resp = client.post("/auth/account", data={
        "current_password": "password123",
        "new_password": "brandnewpassword",
        "confirm_new_password": "brandnewpassword",
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        user = User.query.get(user_id)
        assert user.check_password("brandnewpassword")
        assert not user.check_password("password123")


def test_change_password_rejects_wrong_current_password(app, client):
    user_id, _ = _make_founder_with_profile(app)
    _login(client, "founder@example.com")

    client.post("/auth/account", data={
        "current_password": "wrong-password",
        "new_password": "brandnewpassword",
        "confirm_new_password": "brandnewpassword",
    })

    with app.app_context():
        assert User.query.get(user_id).check_password("password123")


# --- Self-service deletion --------------------------------------------------

def test_delete_project_keeps_account(app, client):
    user_id, profile_id = _make_founder_with_profile(app)
    _login(client, "founder@example.com")

    resp = client.post("/dashboard/project/delete", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert FounderProfile.query.get(profile_id) is None
        assert User.query.get(user_id) is not None


def test_delete_account_requires_correct_password(app, client):
    user_id, _ = _make_founder_with_profile(app)
    _login(client, "founder@example.com")

    client.post("/auth/account/delete", data={"password": "wrong-password"})

    with app.app_context():
        assert User.query.get(user_id) is not None


def test_delete_account_cascades_everything(app, client):
    user_id, profile_id = _make_founder_with_profile(app)
    _login(client, "founder@example.com")

    resp = client.post("/auth/account/delete", data={"password": "password123"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert User.query.get(user_id) is None
        assert FounderProfile.query.get(profile_id) is None
        assert ChatbotConfig.query.filter_by(founder_profile_id=profile_id).first() is None
        assert Donation.query.filter_by(founder_profile_id=profile_id).first() is None

    # session should be logged out — dashboard now redirects to login
    resp = client.get("/dashboard/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


# --- Uploaded files are cleaned up too, not just DB rows -------------------

def test_delete_account_removes_uploaded_files_from_disk(app, client):
    user_id, profile_id = _make_founder_with_profile(app)
    with app.app_context():
        upload_folder = app.config["UPLOAD_FOLDER"]
        deck_dir = os.path.join(upload_folder, "decks")
        os.makedirs(deck_dir, exist_ok=True)
        deck_path = os.path.join(deck_dir, "test-cleanup-deck.pdf")
        with open(deck_path, "wb") as f:
            f.write(b"%PDF-1.4 fake")

        profile = FounderProfile.query.get(profile_id)
        profile.pitch_deck_path = "uploads/decks/test-cleanup-deck.pdf"
        db.session.commit()
        assert os.path.isfile(deck_path)

    _login(client, "founder@example.com")
    client.post("/auth/account/delete", data={"password": "password123"})

    assert not os.path.isfile(deck_path)


# --- Superadmin deletion -----------------------------------------------------

def _make_superadmin(app, email="admin@example.com", password="password123"):
    with app.app_context():
        user = User(email=email, role=UserRole.SUPERADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def test_superadmin_can_delete_any_project(app, client):
    _, profile_id = _make_founder_with_profile(app)
    _make_superadmin(app)
    _login(client, "admin@example.com")

    resp = client.post(f"/superadmin/profile/{profile_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert FounderProfile.query.get(profile_id) is None


def test_superadmin_can_delete_another_users_account(app, client):
    user_id, _ = _make_founder_with_profile(app)
    _make_superadmin(app)
    _login(client, "admin@example.com")

    resp = client.post(f"/superadmin/user/{user_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert User.query.get(user_id) is None


def test_superadmin_cannot_delete_own_account_from_panel(app, client):
    admin_id = _make_superadmin(app)
    _login(client, "admin@example.com")

    resp = client.post(f"/superadmin/user/{admin_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert User.query.get(admin_id) is not None


def test_plain_founder_cannot_use_superadmin_delete_routes(app, client):
    _, profile_id = _make_founder_with_profile(app)
    _login(client, "founder@example.com")

    resp = client.post(f"/superadmin/profile/{profile_id}/delete")
    assert resp.status_code == 403
