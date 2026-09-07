from app import create_app
from app.extensions import db
from app.models import User, FounderProfile, Category, ChatbotConfig, ComplianceScan, Subscription

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "User": User,
        "FounderProfile": FounderProfile,
        "Category": Category,
        "ChatbotConfig": ChatbotConfig,
        "ComplianceScan": ComplianceScan,
        "Subscription": Subscription,
    }


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
