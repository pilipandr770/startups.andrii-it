from datetime import datetime

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required

from app.admin import bp
from app.decorators import admin_required
from app.extensions import db
from app.models import FounderProfile, ProfileStatus
from app.compliance.url_reputation import check_url_reputation


def _refresh_url_reputation(profile):
    """Best-effort — a lookup failure must never block moderation."""
    try:
        status, detail = check_url_reputation(profile.external_url)
        profile.url_reputation_status = status
        profile.url_reputation_detail = detail
        profile.url_reputation_checked_at = datetime.utcnow()
        return status
    except Exception:
        return profile.url_reputation_status


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

    # Re-check right before publishing — the link could have changed, or
    # gone bad, since submission. A flagged link doesn't get auto-published;
    # the moderator has to consciously override (button in admin/queue.html)
    # after looking at the detail, in case it's a false positive. This is
    # about protecting marketplace VISITORS from clicking a malicious link.
    reputation_status = _refresh_url_reputation(profile)
    if reputation_status == "flagged" and not request.form.get("override_reputation_warning"):
        db.session.commit()
        flash(
            f"Not approved: {profile.project_name}'s link was flagged by a malware/phishing "
            "reputation check. Review the details in the queue, then use \"Approve anyway\" "
            "if you're confident this is a false positive.",
            "danger",
        )
        return redirect(url_for("admin.queue"))

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


@bp.route("/profile/<int:profile_id>/recheck-link", methods=["POST"])
@login_required
@admin_required
def recheck_link_reputation(profile_id):
    """Manual re-check — a listing's link reputation isn't static, so this
    is also useful for already-published listings, not just the queue.
    Shared by admin/queue.html and superadmin/index.html."""
    profile = FounderProfile.query.get_or_404(profile_id)
    status = _refresh_url_reputation(profile)
    db.session.commit()
    flash(
        f"Link safety re-checked for {profile.project_name}: {status or 'could not be determined'}.",
        "danger" if status == "flagged" else "info",
    )
    return redirect(request.referrer or url_for("admin.queue"))
