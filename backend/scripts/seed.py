"""Development-only seed data: default organization, admin user, intent
taxonomy, and initial tool allow-list.

Usage:
    python -m scripts.seed

Never run against production. Never embeds real secrets: the admin
password is read from SEED_ADMIN_PASSWORD (see .env.example) and must be
changed after first login in any shared environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from passlib.context import CryptContext  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.agent import Tool  # noqa: E402
from app.models.conversation import Intent  # noqa: E402
from app.models.user import Organization, User, UserRole  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

INTENTS = [
    ("faq", "General frequently-asked question"),
    ("order_tracking", "Customer wants to track an order's status"),
    ("refund", "Customer requests a refund"),
    ("cancellation", "Customer wants to cancel an order or subscription"),
    ("product_search", "Customer is searching for a product"),
    ("product_recommendation", "Customer wants a product recommendation"),
    ("complaint", "Customer is filing a complaint"),
    ("human_agent_request", "Customer explicitly requests a human agent"),
    ("unknown", "Intent could not be confidently classified"),
]

TOOLS = [
    {
        "name": "get_order",
        "description": "Retrieve current status/details for an order by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        "permission": "agent",
        "timeout_seconds": 5,
    },
    {
        "name": "search_product",
        "description": "Search the product catalog by free-text query.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
        "permission": "agent",
        "timeout_seconds": 5,
    },
    {
        "name": "get_product",
        "description": "Retrieve details for a single product by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "string"}},
            "required": ["product_id"],
        },
        "permission": "agent",
        "timeout_seconds": 5,
    },
    {
        "name": "check_refund_policy",
        "description": "Check refund eligibility for an order against policy rules.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        "permission": "agent",
        "timeout_seconds": 5,
    },
    {
        "name": "create_support_ticket",
        "description": "Create a support ticket for follow-up by a human agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["subject", "description"],
        },
        "permission": "agent",
        "timeout_seconds": 5,
    },
]


def seed() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(name="Default Organization").first()
        if not org:
            org = Organization(name="Default Organization")
            db.add(org)
            db.flush()
            print(f"Created organization: {org.id}")

        admin = db.query(User).filter_by(email=settings.seed_admin_email).first()
        if not admin:
            admin = User(
                organization_id=org.id,
                email=settings.seed_admin_email,
                hashed_password=pwd_context.hash(settings.seed_admin_password),
                full_name="Default Admin",
                role=UserRole.admin,
            )
            db.add(admin)
            print(f"Created admin user: {admin.email} (change the password after first login)")

        for name, description in INTENTS:
            if not db.query(Intent).filter_by(name=name).first():
                db.add(Intent(name=name, description=description))

        for tool_def in TOOLS:
            if not db.query(Tool).filter_by(name=tool_def["name"]).first():
                db.add(Tool(**tool_def))

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
