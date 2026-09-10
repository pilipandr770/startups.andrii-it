from datetime import date
from urllib.parse import urlparse

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, URLField, DecimalField, DateField
from wtforms.validators import DataRequired, Length, Optional, URL, ValidationError, NumberRange

from app.models import ProjectStage


def stripe_hosted_link(form, field):
    """
    Anti-scam guard: a donation "payment link" must actually be a Stripe
    Payment Link (hosted on stripe.com), never an arbitrary URL. This is
    what lets us trust the button at all without doing our own KYC — Stripe
    already verified whoever owns that link when they set up their account
    to receive money on it. See docs/ARCHITECTURE.md, "Two separate Stripe
    flows" — the reasoning for why this platform never touches donation
    funds applies equally here: we can only vouch for a link being genuine
    if it's provably Stripe's own domain, checked by hostname suffix (not
    substring, which a link like "buy.stripe.com.evil.example" would defeat).
    """
    if not field.data:
        return
    hostname = (urlparse(field.data).hostname or "").lower()
    if not (hostname == "stripe.com" or hostname.endswith(".stripe.com")):
        raise ValidationError(
            "This must be a Stripe-hosted link (created in your own Stripe "
            "Dashboard under Payment Links — the URL will start with "
            "https://buy.stripe.com/...). We only accept Stripe-hosted "
            "payment links so we can never become a vector for phishing or "
            "wallet-drainer scams."
        )


class ProfileForm(FlaskForm):
    project_name = StringField("Project name", validators=[DataRequired(), Length(max=200)])
    tagline = StringField(
        "Tagline (short, shown on the card)", validators=[Optional(), Length(max=280)]
    )
    description = TextAreaField("Full description", validators=[Optional()])
    category_id = SelectField("Category", coerce=int)
    stage = SelectField("Stage", choices=[(s, s.title()) for s in ProjectStage.ALL])

    external_url = URLField(
        "Link to your live project website (required)",
        validators=[DataRequired(), URL()],
    )
    video_url = URLField(
        "Video URL (YouTube/Vimeo, optional)", validators=[Optional(), URL()]
    )
    banner_image = FileField(
        "Banner image (shown on your marketplace card)",
        validators=[FileAllowed(["png", "jpg", "jpeg", "webp"], "Images only.")],
    )
    pitch_deck = FileField(
        "Pitch deck (PDF, optional)",
        validators=[FileAllowed(["pdf"], "PDF only.")],
    )

    legal_entity_name = StringField(
        "Legal entity name (required before you can accept payments — "
        "this is what Stripe will also verify when you set up your payment link)",
        validators=[Optional(), Length(max=255)],
    )
    funding_goal_text = StringField(
        "Funding / support goal (plain text, e.g. '€5,000 to cover 3 months of dev')",
        validators=[Optional(), Length(max=300)],
    )
    funding_goal_amount = DecimalField(
        "Funding goal amount in EUR (optional — a plain number, powers a progress "
        "bar next to the text above; leave blank to skip the bar)",
        validators=[Optional(), NumberRange(min=0)],
        places=2,
    )
    donation_terms = TextAreaField(
        "What does a supporter get in return? "
        "(Required if you accept donations — must NOT imply equity or profit-share "
        "unless that is a separately structured, regulated offer.)",
        validators=[Optional()],
    )
    founder_stripe_payment_link = URLField(
        "Your own Stripe Payment Link (we redirect visitors here — "
        "we never touch or hold these funds). Create one at "
        "https://dashboard.stripe.com/payment-links/create — must be a "
        "stripe.com link.",
        validators=[Optional(), URL(), stripe_hosted_link],
    )
    founder_contact_email = StringField(
        "Public contact email", validators=[Optional(), Length(max=255)]
    )

    def validate_donation_terms(self, field):
        if self.founder_stripe_payment_link.data and not (field.data or "").strip():
            raise ValidationError(
                "Please describe what a supporter gets in return before adding a donation link."
            )

    def validate_founder_stripe_payment_link(self, field):
        if field.data and not (self.legal_entity_name.data or "").strip():
            raise ValidationError(
                "Add your legal entity name above before accepting payments — "
                "required before any listing can ask visitors for money."
            )


class ChatbotForm(FlaskForm):
    pitch_instructions = TextAreaField(
        "Pitch instructions for your AI assistant. Write in any language — "
        "explain what your project does, who it's for, what you're looking for, "
        "and how to handle common questions. The bot uses this to answer visitors "
        "24/7, in their language, without you needing to be online.",
        validators=[DataRequired(), Length(max=8000)],
    )


class DonationForm(FlaskForm):
    """Logs a supporter contribution the founder saw in their own Stripe
    dashboard — self-reported, see app/models/donation.py."""

    amount = DecimalField(
        "Amount (EUR) — what you saw land in your own Stripe account",
        validators=[DataRequired(), NumberRange(min=0.01)],
        places=2,
    )
    supporter_name = StringField(
        "Supporter name (optional — leave blank to show as Anonymous)",
        validators=[Optional(), Length(max=120)],
    )
    message = StringField(
        "Message from the supporter (optional)",
        validators=[Optional(), Length(max=280)],
    )
    donated_on = DateField("Date", validators=[DataRequired()], default=date.today)
