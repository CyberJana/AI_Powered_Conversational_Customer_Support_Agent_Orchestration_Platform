"""Chat + conversation endpoint tests."""
from unittest.mock import patch


def _signup_and_token(client, email="chatuser@example.com"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Chat User", "role": "customer"},
    )
    return resp.json()["access_token"]


def test_chat_returns_503_without_openai_key(client):
    token = _signup_and_token(client)
    resp = client.post(
        "/api/v1/chat",
        json={"conversation_id": None, "message": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_chat_with_mocked_llm_persists_messages(client):
    token = _signup_and_token(client, email="mocked@example.com")
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="Mocked reply"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.9)),
    ):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "What is my order status?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Mocked reply"
    assert body["intent"] == "faq"
    conversation_id = body["conversation_id"]

    detail = client.get(
        f"/api/v1/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["sender"] == "customer"
    assert messages[1]["sender"] == "assistant"


def test_chat_requires_auth(client):
    resp = client.post("/api/v1/chat", json={"conversation_id": None, "message": "hi"})
    assert resp.status_code == 401


def test_list_conversations_scoped_to_organization(client):
    token = _signup_and_token(client, email="listuser@example.com")
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.9)),
    ):
        client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
    resp = client.get("/api/v1/conversations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_feedback_submission(client):
    token = _signup_and_token(client, email="feedback@example.com")
    with (
        patch("app.services.chat_service.generate_chat_reply", return_value="ok"),
        patch("app.services.intent_service.classify", return_value=("faq", 0.9)),
    ):
        chat_resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
    body = chat_resp.json()
    resp = client.post(
        f"/api/v1/conversations/{body['conversation_id']}/feedback",
        json={"message_id": body["message_id"], "rating": "up", "comment": "great"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
