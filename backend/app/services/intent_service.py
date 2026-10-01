"""Intent detection: classifies an incoming customer message into a fixed
taxonomy (see FR-9 in docs/requirements.md). The taxonomy mirrors
scripts/seed.py's INTENTS so the classifier's output always matches a row
seeded into the `intents` table.
"""
from app.services.llm_service import classify_intent as _classify_intent

INTENT_LABELS = [
    "faq",
    "order_tracking",
    "refund",
    "cancellation",
    "product_search",
    "product_recommendation",
    "complaint",
    "human_agent_request",
    "unknown",
]


def classify(message: str) -> tuple[str, float]:
    """Returns (intent_name, confidence) where intent_name is one of
    INTENT_LABELS. Propagates OpenAIKeyMissingError if no API key is
    configured — intent detection never fabricates a classification.
    """
    return _classify_intent(message, INTENT_LABELS)
