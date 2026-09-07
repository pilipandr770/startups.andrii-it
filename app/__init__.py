import os
from flask import Flask, request, session

from app.config import config_map
from app.extensions import db, login_manager, migrate, babel, csrf


def select_locale():
    if "locale" in session and session["locale"] in ("en", "de"):
        return session["locale"]
    return request.accept_languages.best_match(["en", "de"]) or "en"


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_map.get(config_name, config_map["default"]))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    babel.init_app(app, locale_selector=select_locale)

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Register blueprints ---
    from app.auth import bp as auth_bp
    from app.founder import bp as founder_bp
    from app.marketplace import bp as marketplace_bp
    from app.chatbot import bp as chatbot_bp
    from app.compliance import bp as compliance_bp
    from app.payments import bp as payments_bp
    from app.admin import bp as admin_bp
    from app.superadmin import bp as superadmin_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(founder_bp, url_prefix="/dashboard")
    app.register_blueprint(marketplace_bp, url_prefix="")
    app.register_blueprint(chatbot_bp, url_prefix="/chatbot")
    app.register_blueprint(compliance_bp, url_prefix="/compliance")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(superadmin_bp, url_prefix="/superadmin")

    @app.route("/set-locale/<locale>")
    def set_locale(locale):
        from flask import redirect, url_for
        if locale in ("en", "de"):
            session["locale"] = locale
        return redirect(request.referrer or url_for("marketplace.index"))

    @app.context_processor
    def inject_globals():
        from flask import get_flashed_messages
        return {"current_locale": select_locale()}

    @app.cli.command("seed")
    def seed_command():
        """Seed default categories and the bootstrap superadmin account."""
        from app.seed import run_seed
        run_seed()
        print("Seed complete.")

    return app
