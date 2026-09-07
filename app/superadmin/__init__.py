from flask import Blueprint

bp = Blueprint("superadmin", __name__, template_folder="../templates/superadmin")

from app.superadmin import routes  # noqa: E402,F401
