"""Tool-calling engine tests (Phase 9, FR-12): the allow-listed tool
registry, GET /api/v1/tools, and the tool_service.execute_tool entrypoint
against real (test-seeded) Product/Order/Escalation rows.
"""
import uuid
from unittest.mock import patch

from app.models.agent import Tool
from app.models.commerce import Order, Product


def _signup_and_token(client, email="tooluser@example.com", role="customer"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Tool User", "role": role},
    )
    token = resp.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    return token, me.json()["organization_id"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def _seed_tool(db_session, **overrides):
    defaults = dict(
        name="get_order",
        description="Retrieve current status/details for an order by ID.",
        input_schema={"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
        permission="agent",
        timeout_seconds=5,
        enabled=True,
    )
    defaults.update(overrides)
    tool = Tool(**defaults)
    db_session.add(tool)
    db_session.commit()
    return tool


def test_list_tools_requires_admin(client, db_session):
    _seed_tool(db_session)
    token, _ = _signup_and_token(client, email="plain@example.com", role="customer")
    resp = client.get("/api/v1/tools", headers=_auth(token))
    assert resp.status_code == 403


def test_list_tools_returns_allowlist(client, db_session):
    _seed_tool(db_session)
    _seed_tool(db_session, name="search_product", input_schema={"type": "object", "properties": {}})
    token, _ = _signup_and_token(client, email="toolsadmin@example.com", role="admin")
    resp = client.get("/api/v1/tools", headers=_auth(token))
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert names == {"get_order", "search_product"}


def test_execute_tool_get_order_success(client, db_session):
    _seed_tool(db_session)
    token, org_id = _signup_and_token(client, email="orderowner@example.com")
    order = Order(organization_id=uuid.UUID(org_id), order_number="ORD-1", status="delivered", total_amount=10.0)
    db_session.add(order)
    db_session.commit()

    from app.services import tool_service

    ctx = tool_service.ToolContext(organization_id=uuid.UUID(org_id), conversation_id=uuid.uuid4())
    agent_run_id = uuid.uuid4()
    # agent_run_id has no FK enforcement in sqlite by default; this isolates
    # the handler/validation logic from AgentRun lifecycle, which is covered
    # by the playbook integration test below.
    call = tool_service.execute_tool(db_session, agent_run_id, "get_order", {"order_id": "ORD-1"}, ctx)
    assert call.success is True
    assert call.output["status"] == "delivered"


def test_execute_tool_missing_required_field(client, db_session):
    _seed_tool(db_session)
    token, org_id = _signup_and_token(client, email="missingfield@example.com")

    from app.services import tool_service

    ctx = tool_service.ToolContext(organization_id=uuid.UUID(org_id), conversation_id=uuid.uuid4())
    call = tool_service.execute_tool(db_session, uuid.uuid4(), "get_order", {}, ctx)
    assert call.success is False
    assert "Missing required field" in call.error_message


def test_execute_tool_rejects_disabled_tool(client, db_session):
    _seed_tool(db_session, enabled=False)
    token, org_id = _signup_and_token(client, email="disabledtool@example.com")

    from app.services import tool_service

    ctx = tool_service.ToolContext(organization_id=uuid.UUID(org_id), conversation_id=uuid.uuid4())
    call = tool_service.execute_tool(db_session, uuid.uuid4(), "get_order", {"order_id": "ORD-1"}, ctx)
    assert call.success is False
    assert "not an enabled" in call.error_message


def test_execute_tool_get_order_not_found(client, db_session):
    _seed_tool(db_session)
    token, org_id = _signup_and_token(client, email="notfound@example.com")

    from app.services import tool_service

    ctx = tool_service.ToolContext(organization_id=uuid.UUID(org_id), conversation_id=uuid.uuid4())
    call = tool_service.execute_tool(db_session, uuid.uuid4(), "get_order", {"order_id": "NOPE"}, ctx)
    assert call.success is False
    assert "No order found" in call.error_message


def test_create_support_ticket_creates_escalation(client, db_session):
    _seed_tool(
        db_session,
        name="create_support_ticket",
        description="Create a support ticket for follow-up by a human agent.",
        input_schema={
            "type": "object",
            "properties": {"subject": {"type": "string"}, "description": {"type": "string"}},
            "required": ["subject", "description"],
        },
    )
    token, org_id = _signup_and_token(client, email="ticketowner@example.com")

    from app.models.evaluation import Escalation
    from app.services import tool_service

    conversation_id = uuid.uuid4()
    ctx = tool_service.ToolContext(organization_id=uuid.UUID(org_id), conversation_id=conversation_id)
    call = tool_service.execute_tool(
        db_session,
        uuid.uuid4(),
        "create_support_ticket",
        {"subject": "Broken item", "description": "The item arrived broken.", "priority": "high"},
        ctx,
    )
    assert call.success is True
    assert db_session.query(Escalation).count() == 1


def test_playbook_driven_chat_executes_tool_call(client, db_session):
    token, org_id = _signup_and_token(client, email="playbookchat@example.com", role="admin")
    _seed_tool(db_session)

    agent_resp = client.post(
        "/api/v1/agents",
        json={"name": "Order Bot", "allowed_tools": ["get_order"]},
        headers=_auth(token),
    )
    agent_id = agent_resp.json()["id"]

    client.post(
        "/api/v1/playbooks",
        json={
            "agent_id": agent_id,
            "name": "Order Tracking",
            "intent": "order_tracking",
            "steps": [
                {"type": "tool_call", "config": {"tool": "get_order"}},
                {"type": "respond", "config": {}},
            ],
        },
        headers=_auth(token),
    )

    order = Order(organization_id=uuid.UUID(org_id), order_number="ORD-9", status="shipped", total_amount=25.0)
    db_session.add(order)
    db_session.commit()

    with (
        patch("app.services.chat_service.intent_service.classify", return_value=("order_tracking", 0.9)),
        patch(
            "app.services.chat_service.extract_tool_arguments",
            return_value={"order_id": "ORD-9"},
        ),
        patch("app.services.chat_service.generate_grounded_reply", return_value="Your order is on its way."),
    ):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "Where is my order ORD-9?", "agent_id": agent_id},
            headers=_auth(token),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Your order is on its way."
    assert body["intent"] == "order_tracking"

    from app.models.agent import AgentRun, ToolCall

    runs = db_session.query(AgentRun).all()
    assert len(runs) == 1
    assert runs[0].status == "completed"
    calls = db_session.query(ToolCall).all()
    assert len(calls) == 1
    assert calls[0].success is True
    assert calls[0].output["status"] == "shipped"


def test_product_tools_and_refund_policy(client, db_session):
    _seed_tool(
        db_session,
        name="search_product",
        description="Search the product catalog by free-text query.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
    )
    _seed_tool(
        db_session,
        name="get_product",
        description="Retrieve details for a single product by ID.",
        input_schema={"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]},
    )
    _seed_tool(
        db_session,
        name="check_refund_policy",
        description="Check refund eligibility for an order against policy rules.",
        input_schema={"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    )
    token, org_id = _signup_and_token(client, email="producttools@example.com")

    product = Product(organization_id=uuid.UUID(org_id), sku="SKU-1", name="Widget", price=9.99, stock_quantity=5)
    eligible_order = Order(
        organization_id=uuid.UUID(org_id), order_number="ORD-ELIGIBLE", status="delivered", total_amount=9.99
    )
    ineligible_order = Order(
        organization_id=uuid.UUID(org_id), order_number="ORD-PLACED", status="placed", total_amount=9.99
    )
    db_session.add_all([product, eligible_order, ineligible_order])
    db_session.commit()

    from app.services import tool_service

    ctx = tool_service.ToolContext(organization_id=uuid.UUID(org_id), conversation_id=uuid.uuid4())

    search_call = tool_service.execute_tool(db_session, uuid.uuid4(), "search_product", {"query": "Widget"}, ctx)
    assert search_call.success is True
    assert search_call.output["results"][0]["product_id"] == "SKU-1"

    get_call = tool_service.execute_tool(db_session, uuid.uuid4(), "get_product", {"product_id": "SKU-1"}, ctx)
    assert get_call.success is True
    assert get_call.output["name"] == "Widget"

    eligible_call = tool_service.execute_tool(
        db_session, uuid.uuid4(), "check_refund_policy", {"order_id": "ORD-ELIGIBLE"}, ctx
    )
    assert eligible_call.output["eligible"] is True

    ineligible_call = tool_service.execute_tool(
        db_session, uuid.uuid4(), "check_refund_policy", {"order_id": "ORD-PLACED"}, ctx
    )
    assert ineligible_call.output["eligible"] is False
