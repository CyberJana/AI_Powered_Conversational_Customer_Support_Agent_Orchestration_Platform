"""Escalation queue endpoint tests (Phase 10, FR-14)."""
import uuid
from unittest.mock import patch

from app.models.conversation import Conversation
from app.models.evaluation import Escalation


def _signup_and_token(client, email, role="customer"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Esc User", "role": role},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def _start_conversation(client, token):
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.chat_service.intent_service.classify", return_value=("faq", 0.95)),
    ):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "hi"},
            headers=_auth(token),
        )
    return resp.json()["conversation_id"]


def test_create_escalation_requires_own_conversation(client):
    owner_token = _signup_and_token(client, "escowner@example.com", role="customer")
    conversation_id = _start_conversation(client, owner_token)

    other_token = _signup_and_token(client, "escother@example.com", role="customer")
    resp = client.post(
        "/api/v1/escalations",
        json={"conversation_id": conversation_id, "reason": "Need help"},
        headers=_auth(other_token),
    )
    assert resp.status_code == 404  # different org, so conversation isn't found


def test_create_escalation_success(client):
    token = _signup_and_token(client, "esccreate@example.com", role="customer")
    conversation_id = _start_conversation(client, token)

    resp = client.post(
        "/api/v1/escalations",
        json={"conversation_id": conversation_id, "reason": "Please connect me to a human"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["conversation_id"] == conversation_id


def test_list_escalations_requires_agent_or_admin(client):
    token = _signup_and_token(client, "esclistcustomer@example.com", role="customer")
    resp = client.get("/api/v1/escalations", headers=_auth(token))
    assert resp.status_code == 403


def test_list_escalations_scoped_to_organization(client, db_session):
    agent_token = _signup_and_token(client, "esclistagent@example.com", role="agent")
    me = client.get("/api/v1/auth/me", headers=_auth(agent_token)).json()
    agent_org_id = uuid.UUID(me["organization_id"])

    # Seed a conversation + escalation directly in the agent's own org so we
    # can verify a true positive (same-org) listing, not just empty results.
    same_org_conversation = Conversation(organization_id=agent_org_id, status="escalated")
    db_session.add(same_org_conversation)
    db_session.commit()
    db_session.add(Escalation(conversation_id=same_org_conversation.id, reason="Same-org escalation"))
    db_session.commit()

    same_org_resp = client.get("/api/v1/escalations", headers=_auth(agent_token))
    assert same_org_resp.status_code == 200
    assert len(same_org_resp.json()) == 1
    assert same_org_resp.json()[0]["reason"] == "Same-org escalation"

    other_org_agent_token = _signup_and_token(client, "esclistotherorg@example.com", role="agent")
    other_resp = client.get("/api/v1/escalations", headers=_auth(other_org_agent_token))
    assert other_resp.json() == []


def test_resolve_escalation_cross_org_forbidden(client):
    token = _signup_and_token(client, "escresolve@example.com", role="customer")
    conversation_id = _start_conversation(client, token)
    create_resp = client.post(
        "/api/v1/escalations",
        json={"conversation_id": conversation_id, "reason": "Help"},
        headers=_auth(token),
    )
    escalation_id = create_resp.json()["id"]

    agent_token = _signup_and_token(client, "escresolveagent@example.com", role="agent")
    # Different organizations -> agent can't see/resolve this escalation.
    forbidden_resp = client.post(f"/api/v1/escalations/{escalation_id}/resolve", headers=_auth(agent_token))
    assert forbidden_resp.status_code == 404


def test_resolve_escalation_success(client, db_session):
    agent_token = _signup_and_token(client, "escresolvesuccess@example.com", role="agent")
    me = client.get("/api/v1/auth/me", headers=_auth(agent_token)).json()
    agent_org_id = uuid.UUID(me["organization_id"])
    agent_id = uuid.UUID(me["id"])

    conversation = Conversation(organization_id=agent_org_id, status="escalated")
    db_session.add(conversation)
    db_session.commit()
    escalation = Escalation(conversation_id=conversation.id, reason="Needs a human")
    db_session.add(escalation)
    db_session.commit()

    resp = client.post(f"/api/v1/escalations/{escalation.id}/resolve", headers=_auth(agent_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["assigned_to"] == str(agent_id)
    assert body["resolved_at"] is not None
