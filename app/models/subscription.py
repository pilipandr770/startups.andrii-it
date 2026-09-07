from datetime import datetime
from app.extensions import db


class SubscriptionPlan:
    """Billing period, independent of feature tier (see SubscriptionTier)."""

    MONTHLY = "monthly"
    ANNUAL = "annual"

    ALL = [MONTHLY, ANNUAL]


class SubscriptionTier:
    """
    Feature tier, independent of billing period. Cumulative — each tier
    includes everything in the tier(s) below it:
      presentation -> just the public listing/card
      ai_pitch     -> + the AI pitch assistant actually answers visitors
      payments     -> + the donation/support button is shown and works

    A profile without an active subscription at all, or on a lower tier
    than a feature requires, simply doesn't get that feature — enforced in
    both the templates (hide the UI) and the routes (refuse the action),
    since a determined visitor could otherwise hit a route directly.
    """

    PRESENTATION = "presentation"
    AI_PITCH = "ai_pitch"
    PAYMENTS = "payments"

    ALL = [PRESENTATION, AI_PITCH, PAYMENTS]

    ORDER = {PRESENTATION: 0, AI_PITCH: 1, PAYMENTS: 2}

    LABELS = {
        PRESENTATION: "Presentation",
        AI_PITCH: "Presentation + AI Pitcher",
        PAYMENTS: "Presentation + AI Pitcher + Payments",
    }


class SubscriptionStatus:
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Subscription(db.Model):
    """
    The PLATFORM subscription: founder pays ANDRII (via his own Stripe
    account) for the listing and, depending on tier, the AI pitch assistant
    and/or the donation/payment button. Fully separate from any donation
    flow on the founder's own project page — see app/payments/README in
    code comments and docs/ARCHITECTURE.md, "Two separate Stripe flows".
    """

    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    founder_profile_id = db.Column(
        db.Integer, db.ForeignKey("founder_profiles.id"), nullable=False, unique=True
    )

    plan = db.Column(db.String(20), default=SubscriptionPlan.MONTHLY)  # billing period
    tier = db.Column(db.String(20), default=SubscriptionTier.PRESENTATION)  # feature tier
    status = db.Column(db.String(20), default=SubscriptionStatus.TRIAL)

    stripe_customer_id = db.Column(db.String(120), nullable=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True)

    current_period_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_active(self):
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)

    def has_feature(self, required_tier):
        if not self.is_active:
            return False
        return SubscriptionTier.ORDER.get(self.tier, 0) >= SubscriptionTier.ORDER.get(required_tier, 0)

    def __repr__(self):
        return f"<Subscription {self.tier}/{self.plan}/{self.status} for profile {self.founder_profile_id}>"
