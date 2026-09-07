from flask import Blueprint

bp = Blueprint("compliance", __name__)

from app.compliance import routes  # noqa: E402,F401
