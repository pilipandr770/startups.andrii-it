import os
import re
import uuid

from flask import render_template, redirect, url_for, flash, current_app, abort, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.founder import bp
from app.founder.forms import ProfileForm, ChatbotForm, DonationForm
from app.extensions import db
from app.models import (
    FounderProfile, ChatbotConfig, Category, ProfileStatus, Subscription,
    SubscriptionTier, Donation,
)


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", text)


def save_upload(file_storage, subfolder):
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, unique_name)
    file_storage.save(path)
    return f"uploads/{subfolder}/{unique_name}"


@bp.route("/")
@login_required
def dashboard():
    profile = current_user.founder_profile
    return render_template("founder/dashboard.html", profile=profile)


@bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    profile = current_user.founder_profile
    form = ProfileForm(obj=profile)
    form.category_id.choices = [(c.id, c.name_en) for c in Category.query.order_by(Category.name_en)]
    if request.method == "GET":
        form.legal_entity_name.data = current_user.legal_entity_name
        if profile and profile.funding_goal_amount_cents:
            form.funding_goal_amount.data = profile.funding_goal_amount_cents / 100

    if form.validate_on_submit():
        is_new = profile is None
        if is_new:
            base_slug = slugify(form.project_name.data) or f"project-{uuid.uuid4().hex[:6]}"
            slug = base_slug
            i = 1
            while FounderProfile.query.filter_by(slug=slug).first():
                i += 1
                slug = f"{base_slug}-{i}"
            profile = FounderProfile(user_id=current_user.id, slug=slug)
            db.session.add(profile)

        profile.project_name = form.project_name.data
        profile.tagline = form.tagline.data
        profile.description = form.description.data
        profile.category_id = form.category_id.data
        profile.stage = form.stage.data
        profile.external_url = form.external_url.data
        profile.video_url = form.video_url.data
        current_user.legal_entity_name = form.legal_entity_name.data.strip() or None
        profile.funding_goal_text = form.funding_goal_text.data
        profile.funding_goal_amount_cents = (
            int(form.funding_goal_amount.data * 100) if form.funding_goal_amount.data else None
        )
        profile.donation_terms = form.donation_terms.data
        profile.founder_stripe_payment_link = form.founder_stripe_payment_link.data
        profile.founder_contact_email = form.founder_contact_email.data

        banner_path = save_upload(form.banner_image.data, "banners")
        if banner_path:
            profile.banner_image_path = banner_path

        deck_path = save_upload(form.pitch_deck.data, "decks")
        if deck_path:
            profile.pitch_deck_path = deck_path

        # Any edit to a published (or previously rejected) profile goes back
        # through moderation — re-review on every content change. DRAFT and
        # PENDING_REVIEW are left as-is (already unreviewed / awaiting review).
        if profile.status in (ProfileStatus.PUBLISHED, ProfileStatus.REJECTED):
            profile.status = ProfileStatus.DRAFT

        if is_new:
            db.session.flush()
            db.session.add(Subscription(founder_profile_id=profile.id))

        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("founder.dashboard"))

    return render_template("founder/edit_profile.html", form=form, profile=profile)


@bp.route("/project/delete", methods=["POST"])
@login_required
def delete_project():
    """Deletes the listing only — the account stays, so a founder can start
    a new one later. Cascades to chatbot config, compliance scans,
    subscription, and the supporters log (see FounderProfile relationships)."""
    profile = current_user.founder_profile
    if not profile:
        abort(404)
    project_name = profile.project_name
    db.session.delete(profile)
    db.session.commit()
    flash(f"Deleted: {project_name}.", "info")
    return redirect(url_for("founder.dashboard"))


@bp.route("/profile/submit", methods=["POST"])
@login_required
def submit_for_review():
    profile = current_user.founder_profile
    if not profile:
        abort(404)
    if not profile.external_url:
        flash("Please add your project link before submitting.", "danger")
        return redirect(url_for("founder.edit_profile"))

    profile.status = ProfileStatus.PENDING_REVIEW
    db.session.commit()
    flash("Submitted for review. We'll email you once it's approved.", "success")
    return redirect(url_for("founder.dashboard"))


@bp.route("/chatbot", methods=["GET", "POST"])
@login_required
def chatbot_settings():
    profile = current_user.founder_profile
    if not profile:
        flash("Create your project profile first.", "warning")
        return redirect(url_for("founder.edit_profile"))

    config = profile.chatbot_config or ChatbotConfig(founder_profile_id=profile.id)
    form = ChatbotForm(obj=config)

    if form.validate_on_submit():
        config.pitch_instructions = form.pitch_instructions.data
        config.is_enabled = True
        if not config.id:
            db.session.add(config)
        db.session.commit()
        flash("Chatbot pitch instructions saved.", "success")
        return redirect(url_for("founder.dashboard"))

    return render_template("founder/chatbot.html", form=form, profile=profile)


@bp.route("/supporters", methods=["GET", "POST"])
@login_required
def supporters():
    """Founder-side log of supporter contributions. Self-reported — see
    app/models/donation.py for why this can't be pulled from Stripe
    automatically. Gated behind the Payments tier, same as the public
    donate button itself."""
    profile = current_user.founder_profile
    if not profile:
        flash("Create your project profile first.", "warning")
        return redirect(url_for("founder.edit_profile"))

    if not (profile.subscription and profile.subscription.has_feature(SubscriptionTier.PAYMENTS)):
        flash("Upgrade to the Payments tier to log and show supporters.", "warning")
        return redirect(url_for("founder.dashboard"))

    form = DonationForm()
    if form.validate_on_submit():
        db.session.add(Donation(
            founder_profile_id=profile.id,
            amount_cents=int(form.amount.data * 100),
            supporter_name=(form.supporter_name.data or "").strip() or None,
            message=(form.message.data or "").strip() or None,
            donated_on=form.donated_on.data,
        ))
        db.session.commit()
        flash("Supporter logged.", "success")
        return redirect(url_for("founder.supporters"))

    return render_template("founder/supporters.html", form=form, profile=profile)


@bp.route("/supporters/<int:donation_id>/delete", methods=["POST"])
@login_required
def delete_supporter(donation_id):
    profile = current_user.founder_profile
    donation = Donation.query.get_or_404(donation_id)
    if not profile or donation.founder_profile_id != profile.id:
        abort(404)
    db.session.delete(donation)
    db.session.commit()
    flash("Entry removed.", "info")
    return redirect(url_for("founder.supporters"))
