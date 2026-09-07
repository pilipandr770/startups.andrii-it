from app.extensions import db


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name_en = db.Column(db.String(120), nullable=False)
    name_de = db.Column(db.String(120), nullable=False)

    def name(self, locale="en"):
        return self.name_de if locale == "de" else self.name_en

    def __repr__(self):
        return f"<Category {self.slug}>"


DEFAULT_CATEGORIES = [
    ("compliance-legal", "Compliance & Legal Tech", "Compliance & Legal Tech"),
    ("cybersecurity", "Cybersecurity", "Cybersicherheit"),
    ("fintech", "Fintech", "Fintech"),
    ("healthtech", "HealthTech / Eldercare", "HealthTech / Pflege"),
    ("ecommerce", "E-Commerce", "E-Commerce"),
    ("ai-automation", "AI & Automation", "KI & Automatisierung"),
    ("logistics", "Logistics", "Logistik"),
    ("other", "Other", "Sonstiges"),
]
