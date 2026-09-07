from flask import render_template, redirect, url_for, flash
from flask_login import login_required

from app.superadmin import bp
from app.decorators import superadmin_required
from app.extensions import db
from app.models import User, FounderProfile, Subscription, SubscriptionStatus, SubscriptionTier


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
    from app.models import ProfileStatus

    profile = FounderProfile.query.get_or_404(profile_id)
    profile.status = ProfileStatus.SUSPENDED
    db.session.commit()
    flash(f"Unpublished: {profile.project_name}", "warning")
    return redirect(url_for("superadmin.index"))


@bp.route("/subscription/<int:profile_id>/grant", methods=["POST"])
@login_required
@superadmin_required
def grant_subscription(profile_id):
    """Manually grant/extend a full-tier subscription — e.g. for your own 15
    projects, which are never expected to pay the platform subscription
    themselves but should still get every feature (AI pitcher + payments)."""
    profile = FounderProfile.query.get_or_404(profile_id)
    sub = profile.subscription
    if not sub:
        sub = Subscription(founder_profile_id=profile.id)
        db.session.add(sub)
    sub.status = SubscriptionStatus.ACTIVE
    sub.tier = SubscriptionTier.PAYMENTS
    db.session.commit()
    flash(f"Full-tier subscription granted: {profile.project_name}", "success")
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
