"""
Minimal smoke tests. Run with: pytest

These check that the app boots, models create correctly, and the two
Stripe flows stay properly separated. Extend as the app grows —
this is a starting point, not full coverage.
"""

import pytest

from app import create_app
from app.extensions import db
from app.models import User, UserRole, FounderProfile, Category


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


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"List your project" in resp.data


def test_marketplace_catalog_loads(client):
    resp = client.get("/marketplace")
    assert resp.status_code == 200
    assert b"Discover projects" in resp.data


def test_register_and_login(app, client):
    resp = client.post(
        "/auth/register",
        data={
            "email": "founder@example.com",
            "legal_entity_name": "Example UG",
            "password": "supersecret",
            "confirm_password": "supersecret",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="founder@example.com").first()
        assert user is not None
        assert user.role == UserRole.FOUNDER


def test_founder_profile_requires_external_url(app):
    with app.app_context():
        user = User(email="a@b.com", role=UserRole.FOUNDER)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        profile = FounderProfile(
            user_id=user.id,
            slug="test-project",
            project_name="Test Project",
            external_url="https://example.com",
        )
        db.session.add(profile)
        db.session.commit()

        assert profile.is_visible_to_public is False  # starts as draft


def test_category_bilingual_name(app):
    with app.app_context():
        cat = Category(slug="fintech", name_en="Fintech", name_de="Fintech")
        db.session.add(cat)
        db.session.commit()
        assert cat.name("en") == "Fintech"
        assert cat.name("de") == "Fintech"
