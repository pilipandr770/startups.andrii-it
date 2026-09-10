from datetime import datetime
from app.extensions import db


class ProfileStatus:
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUSPENDED = "suspended"

    ALL = [DRAFT, PENDING_REVIEW, PUBLISHED, REJECTED, SUSPENDED]


class ProjectStage:
    CONCEPT = "concept"
    MVP = "mvp"
    LIVE = "live"
    REVENUE = "revenue"

    ALL = [CONCEPT, MVP, LIVE, REVENUE]


class FounderProfile(db.Model):
    """
    The listing/card a founder manages. This is the discovery layer only —
    the founder's actual product, Impressum, and Datenschutz live on their
    OWN external website (external_url). We link out, we do not host it.
    See docs/ARCHITECTURE.md: "Discovery layer, not a host".
    """

    __tablename__ = "founder_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    project_name = db.Column(db.String(200), nullable=False)
    tagline = db.Column(db.String(280), nullable=True)
    description = db.Column(db.Text, nullable=True)

    stage = db.Column(db.String(20), default=ProjectStage.CONCEPT)

    # External-only content — we never mirror the founder's legal pages.
    external_url = db.Column(db.String(500), nullable=False)
    video_url = db.Column(db.String(500), nullable=True)
    banner_image_path = db.Column(db.String(500), nullable=True)
    pitch_deck_path = db.Column(db.String(500), nullable=True)

    # Donation/support terms — must state clearly this is not equity/investment
    # unless explicitly and separately structured. See docs/ARCHITECTURE.md.
    funding_goal_text = db.Column(db.String(300), nullable=True)
    # Optional structured amount (EUR cents) alongside the free-text goal above
    # — powers the Kickstarter-style progress bar. Free-text stays the primary
    # field since not every founder wants a numeric target.
    funding_goal_amount_cents = db.Column(db.Integer, nullable=True)
    donation_terms = db.Column(db.Text, nullable=True)
    founder_stripe_payment_link = db.Column(db.String(500), nullable=True)
    founder_contact_email = db.Column(db.String(255), nullable=True)

    status = db.Column(db.String(20), default=ProfileStatus.DRAFT, index=True)
    rejection_reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime, nullable=True)

    category = db.relationship("Category")
    chatbot_config = db.relationship(
        "ChatbotConfig", backref="founder_profile", uselist=False, cascade="all, delete-orphan"
    )
    compliance_scans = db.relationship(
        "ComplianceScan", backref="founder_profile", cascade="all, delete-orphan",
        order_by="ComplianceScan.scan_date.desc()",
    )
    subscription = db.relationship(
        "Subscription", backref="founder_profile", uselist=False, cascade="all, delete-orphan"
    )
    donations = db.relationship(
        "Donation", backref="founder_profile", cascade="all, delete-orphan",
        order_by="Donation.donated_on.desc()",
    )

    @property
    def latest_compliance_scan(self):
        return self.compliance_scans[0] if self.compliance_scans else None

    @property
    def is_visible_to_public(self):
        return self.status == ProfileStatus.PUBLISHED

    @property
    def total_raised_cents(self):
        return sum(d.amount_cents for d in self.donations)

    @property
    def supporter_count(self):
        return len(self.donations)

    @property
    def funding_progress_percent(self):
        """None if no numeric goal was set — callers should skip the
        progress bar entirely in that case rather than show 0%."""
        if not self.funding_goal_amount_cents:
            return None
        return min(100, round(self.total_raised_cents / self.funding_goal_amount_cents * 100))

    def __repr__(self):
        return f"<FounderProfile {self.slug} ({self.status})>"
