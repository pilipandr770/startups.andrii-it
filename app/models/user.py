from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class UserRole:
    FOUNDER = "founder"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"

    ALL = [FOUNDER, ADMIN, SUPERADMIN]


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=UserRole.FOUNDER)

    # Legal entity requirement — needed before a founder can accept donations
    # via their own Stripe account (see docs/ARCHITECTURE.md, "Legal separation").
    legal_entity_name = db.Column(db.String(255), nullable=True)
    is_legal_entity_confirmed = db.Column(db.Boolean, default=False)

    is_active_account = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    founder_profile = db.relationship(
        "FounderProfile", backref="owner", uselist=False, cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role in (UserRole.ADMIN, UserRole.SUPERADMIN)

    @property
    def is_superadmin(self):
        return self.role == UserRole.SUPERADMIN

    # Flask-Login expects is_active as an attribute; keep our own explicit flag.
    @property
    def is_active(self):
        return self.is_active_account

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
