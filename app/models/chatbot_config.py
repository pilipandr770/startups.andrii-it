from datetime import datetime
from app.extensions import db


class ChatbotConfig(db.Model):
    """
    Per-project pitch instructions written by the founder. This is the
    system-prompt material for the on-page AI pitch bot: it lets a founder
    "brief" their bot once and have it pitch in any language, any timezone.
    """

    __tablename__ = "chatbot_configs"

    id = db.Column(db.Integer, primary_key=True)
    founder_profile_id = db.Column(
        db.Integer, db.ForeignKey("founder_profiles.id"), nullable=False, unique=True
    )

    pitch_instructions = db.Column(db.Text, nullable=True)
    is_enabled = db.Column(db.Boolean, default=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ChatbotConfig for profile {self.founder_profile_id}>"
