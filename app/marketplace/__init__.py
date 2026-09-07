from flask import Blueprint

bp = Blueprint("marketplace", __name__, template_folder="../templates/marketplace")

from app.marketplace import routes  # noqa: E402,F401
