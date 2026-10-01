"""Continuous learning: review queue capture + approve/reject + promotion
into the evaluation dataset (Phase 13, FR-16).
"""
import uuid
from unittest.mock import patch

from app.evaluation.dataset import INTENT_TEST_CASES
from app.models.agent import Tool
from app.models.learning import ReviewQueueItem


def _signup_and_token(client, email, role="customer"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Learning User", "role": role},
    )
    token = resp.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
    return token, me["organization_id"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def test_low_confidence_chat_captures_review_item(client, db_session):
    token, org_id = _signup_and_token(client, "lowconfcapture@example.com")
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.1)),
    ):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "What are your hours?"},
            headers=_auth(token),
        )
    assert resp.status_code == 200

    items = db_session.query(ReviewQueueItem).filter(ReviewQueueItem.organization_id == uuid.UUID(org_id)).all()
    assert len(items) == 1
    assert items[0].source_type == "low_confidence"
    assert items[0].status == "pending"


def test_negative_feedback_captures_review_item(client, db_session):
    token, org_id = _signup_and_token(client, "negfeedback@example.com")
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.9)),
    ):
        chat_resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "hi"},
            headers=_auth(token),
        )
    body = chat_resp.json()

    feedback_resp = client.post(
        f"/api/v1/conversations/{body['conversation_id']}/feedback",
        json={"message_id": body["message_id"], "rating": "down", "comment": "not helpful"},
        headers=_auth(token),
    )
    assert feedback_resp.status_code == 204

    items = db_session.query(ReviewQueueItem).filter(ReviewQueueItem.organization_id == uuid.UUID(org_id)).all()
    assert len(items) == 1
    assert items[0].source_type == "negative_feedback"


def test_review_queue_requires_agent_or_admin(client):
    token, _ = _signup_and_token(client, "rqcustomer@example.com", role="customer")
    resp = client.get("/api/v1/review-queue", headers=_auth(token))
    assert resp.status_code == 403


def test_approve_review_item_creates_training_example(client, db_session):
    token, org_id = _signup_and_token(client, "approveadmin@example.com", role="admin")

    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.1)),
    ):
        client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "What are your hours?"},
            headers=_auth(token),
        )

    list_resp = client.get("/api/v1/review-queue", headers=_auth(token))
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["source_type"] == "low_confidence"
    item_id = items[0]["id"]

    approve_resp = client.post(
        f"/api/v1/review-queue/{item_id}/approve",
        json={"case_type": "intent", "expected_intent": "faq"},
        headers=_auth(token),
    )
    assert approve_resp.status_code == 201
    example = approve_resp.json()
    assert example["case_type"] == "intent"
    assert example["expected_intent"] == "faq"

    # Re-reviewing is rejected.
    second_resp = client.post(
        f"/api/v1/review-queue/{item_id}/approve",
        json={"case_type": "intent", "expected_intent": "faq"},
        headers=_auth(token),
    )
    assert second_resp.status_code == 409

    list_after = client.get("/api/v1/review-queue?status=pending", headers=_auth(token))
    assert list_after.json() == []


def test_reject_review_item(client):
    token, org_id = _signup_and_token(client, "rejectadmin@example.com", role="admin")
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.1)),
    ):
        client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "What are your hours?"},
            headers=_auth(token),
        )
    item_id = client.get("/api/v1/review-queue", headers=_auth(token)).json()[0]["id"]

    reject_resp = client.post(f"/api/v1/review-queue/{item_id}/reject", headers=_auth(token))
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    examples_resp = client.get("/api/v1/training-examples", headers=_auth(token))
    assert examples_resp.json() == []


def test_promoted_training_example_merged_into_evaluation(client, db_session):
    token, org_id = _signup_and_token(client, "promoteadmin@example.com", role="admin")
    for name, schema in [
        ("get_order", {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}),
        ("get_product", {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}),
        ("search_product", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ("check_refund_policy", {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}),
        (
            "create_support_ticket",
            {
                "type": "object",
                "properties": {"subject": {"type": "string"}, "description": {"type": "string"}},
                "required": ["subject", "description"],
            },
        ),
    ]:
        db_session.add(Tool(name=name, description=name, input_schema=schema, enabled=True))
    db_session.commit()

    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.1)),
    ):
        client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "A brand new custom question"},
            headers=_auth(token),
        )
    item_id = client.get("/api/v1/review-queue", headers=_auth(token)).json()[0]["id"]
    client.post(
        f"/api/v1/review-queue/{item_id}/approve",
        json={"case_type": "intent", "expected_intent": "faq"},
        headers=_auth(token),
    )

    def _mock_classify(message: str):
        expected = {case.message: case.expected_intent for case in INTENT_TEST_CASES}
        if message in expected:
            return expected[message], 0.9
        return "faq", 0.9  # the promoted custom question

    with patch("app.evaluation.runner.intent_service.classify", side_effect=_mock_classify):
        eval_resp = client.post("/api/v1/evaluations/run", json={"name": "Promoted Run"}, headers=_auth(token))

    assert eval_resp.status_code == 201
    body = eval_resp.json()
    assert body["summary"]["promoted_examples_count"] == 1
    assert body["dataset_size"] == len(INTENT_TEST_CASES) + 1 + 7  # +1 promoted intent, +7 fixed tool cases
