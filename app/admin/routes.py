from datetime import datetime

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required

from app.admin import bp
from app.decorators import admin_required
from app.extensions import db
from app.models import FounderProfile, ProfileStatus


@bp.route("/queue")
@login_required
@admin_required
def queue():
    pending = (
        FounderProfile.query.filter_by(status=ProfileStatus.PENDING_REVIEW)
        .order_by(FounderProfile.updated_at.asc())
        .all()
    )
    return render_template("admin/queue.html", profiles=pending)


@bp.route("/profile/<int:profile_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve(profile_id):
    profile = FounderProfile.query.get_or_404(profile_id)
    profile.status = ProfileStatus.PUBLISHED
    profile.published_at = datetime.utcnow()
    profile.rejection_reason = None

    # A human moderator approving a listing that asks for money IS the
    # legal-entity check for this MVP — we don't run our own KYC (Stripe
    # does that for whoever owns the payment link), but we do require a
    # person to have looked at the stated legal entity name before it
    # counts as confirmed. See docs/PROJECT_GOALS.md, "Moderation".
    if profile.founder_stripe_payment_link and profile.owner.legal_entity_name:
        profile.owner.is_legal_entity_confirmed = True

    db.session.commit()
    flash(f"Approved: {profile.project_name}", "success")
    return redirect(url_for("admin.queue"))


@bp.route("/profile/<int:profile_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject(profile_id):
    profile = FounderProfile.query.get_or_404(profile_id)
    profile.status = ProfileStatus.REJECTED
    profile.rejection_reason = request.form.get("reason", "").strip() or None
    db.session.commit()
    flash(f"Rejected: {profile.project_name}", "info")
    return redirect(url_for("admin.queue"))


@bp.route("/profile/<int:profile_id>/suspend", methods=["POST"])
@login_required
@admin_required
def suspend(profile_id):
    profile = FounderProfile.query.get_or_404(profile_id)
    profile.status = ProfileStatus.SUSPENDED
    db.session.commit()
    flash(f"Suspended: {profile.project_name}", "warning")
    return redirect(url_for("admin.queue"))
