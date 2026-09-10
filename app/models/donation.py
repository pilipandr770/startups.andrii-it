from datetime import datetime, date
from app.extensions import db


class Donation(db.Model):
    """
    A supporter contribution logged manually by the founder — NOT verified
    by the platform. We have no API access to the founder's own Stripe
    account (see docs/ARCHITECTURE.md, "Two separate Stripe flows" — adding
    that access via Stripe Connect is explicitly forbidden), so the founder
    is the only party who can actually see the real payment; they report it
    here themselves. Every place this is displayed must make the
    self-reported nature clear — never present it as platform-verified.
    """

    __tablename__ = "donations"

    id = db.Column(db.Integer, primary_key=True)
    founder_profile_id = db.Column(
        db.Integer, db.ForeignKey("founder_profiles.id"), nullable=False, index=True
    )

    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    supporter_name = db.Column(db.String(120), nullable=True)
    message = db.Column(db.String(280), nullable=True)
    donated_on = db.Column(db.Date, nullable=False, default=date.today)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def amount_display(self):
        return f"{self.amount_cents / 100:,.2f}"

    def __repr__(self):
        return f"<Donation {self.amount_cents}c for profile {self.founder_profile_id}>"
