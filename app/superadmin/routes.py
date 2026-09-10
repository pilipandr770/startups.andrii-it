from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.superadmin import bp
from app.decorators import superadmin_required
from app.extensions import db
from app.models import User, FounderProfile, ProfileStatus, Subscription, SubscriptionStatus, SubscriptionTier
from app.founder.routes import delete_profile_uploads


@bp.route("/")
@login_required
@superadmin_required
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    profiles = FounderProfile.query.order_by(FounderProfile.created_at.desc()).all()
    return render_template("superadmin/index.html", users=users, profiles=profiles)


@bp.route("/profile/<int:profile_id>/unpublish", methods=["POST"])
@login_required
@superadmin_required
def unpublish(profile_id):
    profile = FounderProfile.query.get_or_404(profile_id)
    profile.status = ProfileStatus.SUSPENDED
    db.session.commit()
    flash(f"Unpublished: {profile.project_name}", "warning")
    return redirect(url_for("superadmin.index"))


@bp.route("/profile/<int:profile_id>/publish", methods=["POST"])
@login_required
@superadmin_required
def publish(profile_id):
    """Publish directly, skipping the moderation queue — for your own
    projects, where you're both the founder and the moderator."""
    profile = FounderProfile.query.get_or_404(profile_id)
    profile.status = ProfileStatus.PUBLISHED
    profile.published_at = datetime.utcnow()
    profile.rejection_reason = None
    if profile.founder_stripe_payment_link and profile.owner.legal_entity_name:
        profile.owner.is_legal_entity_confirmed = True
    db.session.commit()
    flash(f"Published: {profile.project_name}", "success")
    return redirect(url_for("superadmin.index"))


@bp.route("/subscription/<int:profile_id>/grant", methods=["POST"])
@login_required
@superadmin_required
def grant_subscription(profile_id):
    """Manually set a subscription tier — e.g. for your own ~15 projects,
    which are never expected to pay the platform subscription themselves.
    Lets you pick the tier per project rather than always granting every
    feature (a project you're not ready to accept donations on yet doesn't
    have to jump straight to the Payments tier)."""
    profile = FounderProfile.query.get_or_404(profile_id)
    tier = request.form.get("tier", SubscriptionTier.PAYMENTS)
    if tier not in SubscriptionTier.ALL:
        abort(400)

    sub = profile.subscription
    if not sub:
        sub = Subscription(founder_profile_id=profile.id)
        db.session.add(sub)
    sub.status = SubscriptionStatus.ACTIVE
    sub.tier = tier
    db.session.commit()
    flash(f"Subscription set to '{tier}': {profile.project_name}", "success")
    return redirect(url_for("superadmin.index"))


@bp.route("/subscription/<int:profile_id>/revoke", methods=["POST"])
@login_required
@superadmin_required
def revoke_subscription(profile_id):
    """Cancel a manually-granted subscription — e.g. to test what a founder
    without an active subscription actually sees, or to undo a grant made by
    mistake. Does not unpublish the listing itself (that's ProfileStatus,
    tracked separately) — only removes the AI pitcher / payments features."""
    profile = FounderProfile.query.get_or_404(profile_id)
    sub = profile.subscription
    if sub:
        sub.status = SubscriptionStatus.CANCELLED
        db.session.commit()
        flash(f"Subscription revoked: {profile.project_name}", "warning")
    return redirect(url_for("superadmin.index"))


@bp.route("/user/<int:user_id>/promote-admin", methods=["POST"])
@login_required
@superadmin_required
def promote_to_admin(user_id):
    from app.models import UserRole

    user = User.query.get_or_404(user_id)
    user.role = UserRole.ADMIN
    db.session.commit()
    flash(f"{user.email} is now an admin.", "success")
    return redirect(url_for("superadmin.index"))


@bp.route("/profile/<int:profile_id>/delete", methods=["POST"])
@login_required
@superadmin_required
def delete_profile(profile_id):
    """Removes a listing entirely — e.g. cleaning up a test/abandoned
    project. The owner's account is untouched; use delete_user for that."""
    profile = FounderProfile.query.get_or_404(profile_id)
    project_name = profile.project_name
    delete_profile_uploads(profile)
    db.session.delete(profile)
    db.session.commit()
    flash(f"Deleted project: {project_name}", "warning")
    return redirect(url_for("superadmin.index"))


@bp.route("/user/<int:user_id>/delete", methods=["POST"])
@login_required
@superadmin_required
def delete_user(user_id):
    """Deletes an account and everything tied to it (listing, chatbot
    config, compliance scans, subscription, supporters log). Refuses to
    delete your own logged-in account here to avoid a self-inflicted
    lockout — use the regular account-settings page for that."""
    if user_id == current_user.id:
        flash("Use Account settings to delete your own account.", "warning")
        return redirect(url_for("superadmin.index"))

    user = User.query.get_or_404(user_id)
    email = user.email
    if user.founder_profile:
        delete_profile_uploads(user.founder_profile)
    db.session.delete(user)
    db.session.commit()
    flash(f"Deleted account: {email}", "warning")
    return redirect(url_for("superadmin.index"))
