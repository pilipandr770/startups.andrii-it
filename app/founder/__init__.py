from flask import Blueprint

bp = Blueprint("founder", __name__, template_folder="../templates/founder")

from app.founder import routes  # noqa: E402,F401
