from flask import request, jsonify

from app.chatbot import bp
from app.chatbot.service import get_pitch_response
from app.models import FounderProfile, ProfileStatus, SubscriptionTier
from app.extensions import csrf


@bp.route("/<slug>/message", methods=["POST"])
@csrf.exempt
def send_message(slug):
    # Exempt from CSRF: this is a public, unauthenticated JSON endpoint
    # called via fetch() from anonymous visitors (see static/js/main.js) —
    # there's no session-authenticated action to forge here, which is what
    # CSRF protection exists for. It still needs its own abuse controls
    # (rate limiting) — see docs/STATE.md, "Not started".
    profile = FounderProfile.query.filter_by(slug=slug).first_or_404()
    if profile.status != ProfileStatus.PUBLISHED:
        return jsonify({"error": "This project is not published."}), 404

    # Defense in depth — the widget is also hidden in the template when the
    # tier doesn't include it, but a request could still be sent directly.
    if not (profile.subscription and profile.subscription.has_feature(SubscriptionTier.AI_PITCH)):
        return jsonify({"reply": "This project hasn't unlocked the AI pitch assistant yet."})

    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_message:
        return jsonify({"error": "Message is required."}), 400
    if len(user_message) > 2000:
        return jsonify({"error": "Message too long."}), 400

    reply = get_pitch_response(profile, user_message, conversation_history=history)
    return jsonify({"reply": reply})
