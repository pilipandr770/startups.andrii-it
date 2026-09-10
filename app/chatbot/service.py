"""
Pitch-bot engine.

Design: each published project has a small system prompt written by its
founder (FounderProfile.chatbot_config.pitch_instructions). We wrap that
with a fixed guardrail prompt so the bot:
  - only pitches THIS project, using the founder's own words/facts
  - never invents facts not given by the founder
  - never handles payments directly (always points to the donate button)
  - answers in whatever language the visitor writes in

This is intentionally a thin wrapper — swap the model or add RAG over a
larger knowledge base (FAQ doc, pitch deck text extraction, etc.) here
without touching the route layer.
"""

from flask import current_app

SYSTEM_PROMPT_TEMPLATE = """You are the pitch assistant for the startup "{project_name}".

Answer visitor questions about this project ONLY using the information
below, written by the founder. If you don't know something, say so plainly
and suggest the visitor use the contact email or Stripe donate button on
the page — do not invent facts, numbers, or promises.

Never claim the project offers equity, a share of ownership, or guaranteed
returns unless that is explicitly stated in the founder's information below.
Always reply in the same language the visitor is writing in.

--- Founder-provided project information ---
{pitch_instructions}
--- End of founder-provided information ---
"""


def get_pitch_response(founder_profile, user_message, conversation_history=None):
    """
    Returns the bot's reply as a string.

    conversation_history: optional list of {"role": "user"/"assistant", "content": str}
    """
    config = founder_profile.chatbot_config
    if not config or not config.is_enabled or not config.pitch_instructions:
        return (
            "This project hasn't set up its AI assistant yet. "
            "Please use the contact email on this page, or visit the project's website."
        )

    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        return (
            "[Chatbot not configured: ANTHROPIC_API_KEY is missing in .env. "
            "This is a placeholder response for local development.]"
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            project_name=founder_profile.project_name,
            pitch_instructions=config.pitch_instructions,
        )

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=600,
            system=system_prompt,
            messages=messages,
        )
        text_parts = [block.text for block in response.content if block.type == "text"]
        return "\n".join(text_parts) if text_parts else "(no response)"

    except Exception as exc:  # noqa: BLE001 — surface a friendly error to the widget
        current_app.logger.exception("Chatbot call failed")
        return f"Sorry, the assistant is temporarily unavailable ({exc.__class__.__name__})."
