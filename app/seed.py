"""
Run with: flask seed
Creates default categories and the bootstrap superadmin account
(from SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD in .env), if not already present.
"""

from flask import current_app

from app.extensions import db
from app.models import Category, DEFAULT_CATEGORIES, User, UserRole


def run_seed():
    for slug, name_en, name_de in DEFAULT_CATEGORIES:
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(slug=slug, name_en=name_en, name_de=name_de))

    admin_email = current_app.config["SUPERADMIN_EMAIL"]
    if not User.query.filter_by(email=admin_email).first():
        admin = User(email=admin_email, role=UserRole.SUPERADMIN)
        admin.set_password(current_app.config["SUPERADMIN_PASSWORD"])
        db.session.add(admin)

    db.session.commit()
