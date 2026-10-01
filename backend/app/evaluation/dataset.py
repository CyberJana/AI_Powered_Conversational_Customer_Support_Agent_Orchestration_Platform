"""Fixed, human-labeled evaluation dataset (FR-15): a small but real set of
customer-support utterances with a ground-truth intent label, used by
app.evaluation.runner to measure the live intent classifier's accuracy.

This is analogous to a hand-written unit test fixture - the labels are
authored ground truth, not generated/fabricated at evaluation time, and the
classifier's output is always a real LLM call (never mocked here).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentTestCase:
    id: str
    message: str
    expected_intent: str


@dataclass(frozen=True)
class ToolTestCase:
    """A tool invocation whose expected outcome is tied to the demo data
    scripts/seed.py seeds for the "Default Organization" (SKU-100..300,
    ORD-1001..1003). Running against an organization without that seeded
    data will honestly report failures rather than fabricate a pass.
    """

    id: str
    tool_name: str
    input: dict
    expect_success: bool


INTENT_TEST_CASES: list[IntentTestCase] = [
    IntentTestCase("intent-faq-1", "What are your business hours?", "faq"),
    IntentTestCase("intent-faq-2", "Do you ship internationally?", "faq"),
    IntentTestCase("intent-order-1", "Where is my order ORD-1002?", "order_tracking"),
    IntentTestCase("intent-order-2", "Can you give me a status update on my package?", "order_tracking"),
    IntentTestCase("intent-refund-1", "I'd like a refund for my last purchase.", "refund"),
    IntentTestCase("intent-refund-2", "This item is defective, I want my money back.", "refund"),
    IntentTestCase("intent-cancel-1", "Please cancel my order before it ships.", "cancellation"),
    IntentTestCase("intent-cancel-2", "I want to cancel my subscription.", "cancellation"),
    IntentTestCase("intent-search-1", "Do you have any wireless headphones in stock?", "product_search"),
    IntentTestCase("intent-search-2", "Looking for a mechanical keyboard under $100.", "product_search"),
    IntentTestCase("intent-rec-1", "What would you recommend for a gift under $30?", "product_recommendation"),
    IntentTestCase("intent-complaint-1", "This is the third time my order has arrived late, I'm furious.", "complaint"),
    IntentTestCase("intent-complaint-2", "Your customer service has been terrible.", "complaint"),
    IntentTestCase("intent-human-1", "I want to talk to a real person right now.", "human_agent_request"),
    IntentTestCase("intent-human-2", "Please connect me with a human agent.", "human_agent_request"),
    IntentTestCase("intent-unknown-1", "asdkjhasdkjh qwoieqwoe", "unknown"),
]

TOOL_TEST_CASES: list[ToolTestCase] = [
    ToolTestCase("tool-get-order-ok", "get_order", {"order_id": "ORD-1001"}, True),
    ToolTestCase("tool-get-order-missing", "get_order", {"order_id": "ORD-9999"}, False),
    ToolTestCase("tool-get-product-ok", "get_product", {"product_id": "SKU-100"}, True),
    ToolTestCase("tool-get-product-missing", "get_product", {"product_id": "SKU-999"}, False),
    ToolTestCase("tool-search-product-ok", "search_product", {"query": "Keyboard"}, True),
    ToolTestCase("tool-refund-check-ok", "check_refund_policy", {"order_id": "ORD-1001"}, True),
    ToolTestCase("tool-create-ticket-missing-field", "create_support_ticket", {"subject": "Help"}, False),
]
