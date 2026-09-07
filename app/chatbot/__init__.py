from flask import Blueprint

bp = Blueprint("chatbot", __name__)

from app.chatbot import routes  # noqa: E402,F401
