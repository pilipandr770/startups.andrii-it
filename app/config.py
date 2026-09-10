import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    # Flask-WTF defaults this to 3600s (1 hour). The profile-edit form is long
    # and often involves a side-trip to Stripe to grab a payment link before
    # coming back to paste it in — a 1-hour window is too easy to blow past,
    # which surfaces as an ugly unstyled "CSRF token has expired" page. None
    # disables the time-based expiry; the token is still session-bound, which
    # is the actual CSRF defense.
    WTF_CSRF_TIME_LIMIT = None
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(basedir, "dev.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(basedir, "app", "static", "uploads")
    )
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 15)) * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_DOC_EXTENSIONS = {"pdf"}

    LANGUAGES = ["en", "de"]
    BABEL_DEFAULT_LOCALE = os.environ.get("DEFAULT_LOCALE", "en")
    BABEL_TRANSLATION_DIRECTORIES = "translations"

    # Platform subscription Stripe (YOUR account — founders pay YOU for listing,
    # and depending on tier, the AI pitcher and/or the donation button).
    STRIPE_PLATFORM_SECRET_KEY = os.environ.get("STRIPE_PLATFORM_SECRET_KEY", "")
    STRIPE_PLATFORM_PUBLISHABLE_KEY = os.environ.get("STRIPE_PLATFORM_PUBLISHABLE_KEY", "")
    STRIPE_PLATFORM_WEBHOOK_SECRET = os.environ.get("STRIPE_PLATFORM_WEBHOOK_SECRET", "")

    # One Stripe Price ID per (tier, billing period) — create these as
    # recurring Prices in your own Stripe Dashboard. Keyed exactly like
    # SubscriptionTier.ALL x SubscriptionPlan.ALL so payments/platform_subscription.py
    # can look them up as STRIPE_PLATFORM_PRICE_IDS[(tier, period)].
    STRIPE_PLATFORM_PRICE_IDS = {
        (tier, period): os.environ.get(
            f"STRIPE_PLATFORM_PRICE_ID_{tier.upper()}_{period.upper()}", ""
        )
        for tier in ("presentation", "ai_pitch", "payments")
        for period in ("monthly", "annual")
    }

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

    # Optional — protects marketplace VISITORS by checking a founder's
    # external_url against malware/phishing reputation databases before
    # (and periodically after) their listing goes live. URLhaus needs no
    # key and always runs; these two add more coverage when set. See
    # app/compliance/url_reputation.py.
    GOOGLE_SAFE_BROWSING_API_KEY = os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY", "")
    VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", "")

    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

    SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL", "admin@example.com")
    SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", "change-me")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    # Tests must stay network-free regardless of what a developer's local
    # .env happens to have configured — see tests/test_url_reputation.py.
    GOOGLE_SAFE_BROWSING_API_KEY = ""
    VIRUSTOTAL_API_KEY = ""


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
