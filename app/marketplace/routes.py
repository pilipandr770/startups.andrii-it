from flask import render_template, request, abort

from app.marketplace import bp
from app.models import FounderProfile, Category, ProfileStatus, ProjectStage


@bp.route("/")
def home():
    """Marketing landing page — explains what this is and for whom, with a
    CTA into either side of the marketplace. The actual catalog lives at
    marketplace.index (/marketplace)."""
    published_count = FounderProfile.query.filter_by(status=ProfileStatus.PUBLISHED).count()
    return render_template("marketplace/home.html", published_count=published_count)


@bp.route("/marketplace")
def index():
    category_slug = request.args.get("category")
    stage = request.args.get("stage")

    query = FounderProfile.query.filter_by(status=ProfileStatus.PUBLISHED)

    if category_slug:
        query = query.join(Category).filter(Category.slug == category_slug)
    if stage in ProjectStage.ALL:
        query = query.filter(FounderProfile.stage == stage)

    profiles = query.order_by(FounderProfile.published_at.desc()).all()
    categories = Category.query.order_by(Category.name_en).all()

    return render_template(
        "marketplace/index.html",
        profiles=profiles,
        categories=categories,
        stages=ProjectStage.ALL,
        active_category=category_slug,
        active_stage=stage,
    )


@bp.route("/p/<slug>")
def project_detail(slug):
    profile = FounderProfile.query.filter_by(slug=slug).first_or_404()

    # Only published projects are publicly visible; founders can preview their
    # own draft/pending profile.
    from flask_login import current_user

    is_owner = current_user.is_authenticated and profile.user_id == current_user.id
    is_staff = current_user.is_authenticated and current_user.is_admin

    if not profile.is_visible_to_public and not (is_owner or is_staff):
        abort(404)

    return render_template("marketplace/project.html", profile=profile)
