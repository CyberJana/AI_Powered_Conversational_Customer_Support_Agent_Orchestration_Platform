"""Evaluation harness endpoint tests (Phase 12, FR-15)."""
import uuid
from unittest.mock import patch

from app.evaluation.dataset import INTENT_TEST_CASES, TOOL_TEST_CASES
from app.models.agent import Tool
from app.models.commerce import Order, Product


def _signup_and_token(client, email, role="admin"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Eval User", "role": role},
    )
    token = resp.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
    return token, me["organization_id"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def _seed_tools(db_session):
    seeded = [
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
    ]
    for name, schema in seeded:
        db_session.add(Tool(name=name, description=name, input_schema=schema, enabled=True))
    db_session.commit()


def _seed_commerce(db_session, org_id):
    db_session.add(Product(organization_id=org_id, sku="SKU-100", name="Headphones", price=10.0, stock_quantity=5))
    db_session.add(
        Order(organization_id=org_id, order_number="ORD-1001", status="delivered", total_amount=10.0)
    )
    db_session.commit()


def _mock_classify(message: str):
    expected = {case.message: case.expected_intent for case in INTENT_TEST_CASES}
    return expected.get(message, "unknown"), 0.9


def test_trigger_evaluation_requires_admin(client):
    token, _ = _signup_and_token(client, "evalcustomer@example.com", role="customer")
    resp = client.post("/api/v1/evaluations/run", json={"name": "Test Run"}, headers=_auth(token))
    assert resp.status_code == 403


def test_trigger_evaluation_runs_and_persists_summary(client, db_session):
    token, org_id = _signup_and_token(client, "evaladmin@example.com")
    _seed_tools(db_session)
    _seed_commerce(db_session, uuid.UUID(org_id))

    with patch("app.evaluation.runner.intent_service.classify", side_effect=_mock_classify):
        resp = client.post("/api/v1/evaluations/run", json={"name": "Nightly Run"}, headers=_auth(token))

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert body["dataset_size"] == len(INTENT_TEST_CASES) + len(TOOL_TEST_CASES)
    assert body["summary"]["intent_accuracy"] == 1.0
    assert "tool_success_rate" in body["summary"]
    assert "token_usage" in body["summary"]
    assert body["summary"]["token_usage"]["total_tokens"] == 0  # no real LLM call was made (mocked classify)


def test_trigger_evaluation_rejects_unknown_knowledge_base(client, db_session):
    token, org_id = _signup_and_token(client, "evalkb@example.com")
    _seed_tools(db_session)
    fake_kb_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"name": "KB Run", "knowledge_base_id": fake_kb_id},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_list_and_get_evaluation_scoped_to_org(client, db_session):
    token, org_id = _signup_and_token(client, "evallist@example.com")
    _seed_tools(db_session)

    with patch("app.evaluation.runner.intent_service.classify", side_effect=_mock_classify):
        create_resp = client.post("/api/v1/evaluations/run", json={"name": "Run A"}, headers=_auth(token))
    evaluation_id = create_resp.json()["id"]

    list_resp = client.get("/api/v1/evaluations", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    detail_resp = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=_auth(token))
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["results"]) == len(INTENT_TEST_CASES) + len(TOOL_TEST_CASES)

    other_token, _ = _signup_and_token(client, "evalotherorg@example.com")
    other_list_resp = client.get("/api/v1/evaluations", headers=_auth(other_token))
    assert other_list_resp.json() == []
    other_detail_resp = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=_auth(other_token))
    assert other_detail_resp.status_code == 404
