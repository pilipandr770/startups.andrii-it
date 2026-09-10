"""
Tests for the moderation status machine on profile edits. See
docs/ARCHITECTURE.md, "Roles and moderation" — editing a published profile
only resets it to draft if a *substantive* field changed (name, link,
funding claims, donation terms, payment link, contact email — the things
admin/queue.html actually shows a moderator). Cosmetic changes (banner,
pitch deck, tagline, description, video, category/stage) do not force
re-review. Two things this guards against regressing:
  1. A prior bug checked the wrong status tuple (DRAFT/REJECTED instead of
     PUBLISHED/REJECTED), so an edit to a *live* published listing silently
     stayed published with unreviewed content.
  2. The original "ANY edit resets to draft" rule was real friction in
     practice — a founder uploading a new pitch deck PDF unpublished their
     whole listing, which read as a bug even though it was intentional.
"""

import io

import pytest

from app import create_app
from app.extensions import db
from app.models import User, UserRole, FounderProfile, ProfileStatus, Category


@pytest.fixture
def app():
    # Deliberately NOT held open across `yield` — Flask's RequestContext
    # reuses an already-active app context for the same app instead of
    # pushing a fresh one, so client.post() calls here would all share one
    # stale SQLAlchemy session/identity-map with any direct db.session
    # mutation done between them (see _set_profile_status below), producing
    # test-only false failures that don't reflect real request handling
    # (each real HTTP request always gets its own fresh context/session).
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


def _register_and_get_category_id(app, client):
    client.post("/auth/register", data={
        "email": "founder@example.com",
        "legal_entity_name": "",
        "password": "supersecret",
        "confirm_password": "supersecret",
    }, follow_redirects=True)
    with app.app_context():
        return Category.query.first().id


def _edit_profile_form_data(category_id, **overrides):
    data = {
        "project_name": "Test Project",
        "tagline": "",
        "description": "",
        "category_id": str(category_id),
        "stage": "concept",
        "external_url": "https://example.com",
        "video_url": "",
        "legal_entity_name": "",
        "funding_goal_text": "",
        "donation_terms": "",
        "founder_stripe_payment_link": "",
        "founder_contact_email": "",
        "banner_image": (io.BytesIO(b""), ""),
        "pitch_deck": (io.BytesIO(b""), ""),
    }
    data.update(overrides)
    return data


def _set_profile_status(app, status):
    with app.app_context():
        profile = FounderProfile.query.first()
        profile.status = status
        db.session.commit()


def test_editing_published_profile_with_substantive_change_resets_to_draft(app, client):
    category_id = _register_and_get_category_id(app, client)
    client.post("/dashboard/profile/edit", data=_edit_profile_form_data(category_id),
                content_type="multipart/form-data", follow_redirects=True)
    _set_profile_status(app, ProfileStatus.PUBLISHED)

    resp = client.post(
        "/dashboard/profile/edit",
        data=_edit_profile_form_data(category_id, external_url="https://a-different-site.example"),
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        profile = FounderProfile.query.first()
        assert profile.status == ProfileStatus.DRAFT
        assert profile.external_url == "https://a-different-site.example"


def test_editing_published_profile_with_only_cosmetic_change_stays_published(app, client):
    category_id = _register_and_get_category_id(app, client)
    client.post("/dashboard/profile/edit", data=_edit_profile_form_data(category_id),
                content_type="multipart/form-data", follow_redirects=True)
    _set_profile_status(app, ProfileStatus.PUBLISHED)

    # Only tagline changes — this is what a founder uploading a new pitch
    # deck PDF or banner (also cosmetic) experiences.
    resp = client.post(
        "/dashboard/profile/edit",
        data=_edit_profile_form_data(category_id, tagline="A snappier one-liner"),
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        profile = FounderProfile.query.first()
        assert profile.status == ProfileStatus.PUBLISHED
        assert profile.tagline == "A snappier one-liner"


def test_editing_rejected_profile_resets_to_draft(app, client):
    category_id = _register_and_get_category_id(app, client)
    client.post("/dashboard/profile/edit", data=_edit_profile_form_data(category_id),
                content_type="multipart/form-data", follow_redirects=True)
    _set_profile_status(app, ProfileStatus.REJECTED)

    client.post("/dashboard/profile/edit", data=_edit_profile_form_data(category_id),
                content_type="multipart/form-data", follow_redirects=True)

    with app.app_context():
        assert FounderProfile.query.first().status == ProfileStatus.DRAFT


def test_editing_pending_review_profile_stays_pending(app, client):
    category_id = _register_and_get_category_id(app, client)
    client.post("/dashboard/profile/edit", data=_edit_profile_form_data(category_id),
                content_type="multipart/form-data", follow_redirects=True)
    _set_profile_status(app, ProfileStatus.PENDING_REVIEW)

    client.post("/dashboard/profile/edit", data=_edit_profile_form_data(category_id),
                content_type="multipart/form-data", follow_redirects=True)

    with app.app_context():
        assert FounderProfile.query.first().status == ProfileStatus.PENDING_REVIEW
