"""RAG retrieval tests: chat grounded in knowledge-base document chunks."""
from unittest.mock import patch


def _signup_and_token(client, email="raguser@example.com", role="admin"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "RAG User", "role": role},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def _create_kb_with_document(client, token, embedding):
    kb_id = client.post("/api/v1/knowledge-bases", json={"name": "Policies"}, headers=_auth(token)).json()["id"]
    with patch("app.services.ingestion_service.generate_embeddings", return_value=[embedding]):
        client.post(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            files={"file": ("policy.txt", b"Refunds are processed within 5 business days.", "text/plain")},
            headers=_auth(token),
        )
    return kb_id


def test_chat_with_sufficient_context_returns_grounded_answer_and_sources(client):
    token = _signup_and_token(client, email="grounded@example.com")
    kb_id = _create_kb_with_document(client, token, embedding=[1.0, 0.0, 0.0])

    with (
        patch("app.services.rag_service.generate_embeddings", return_value=[[1.0, 0.0, 0.0]]),
        patch("app.services.chat_service.generate_grounded_reply", return_value="Refunds take 5 days [1]."),
    ):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "How long do refunds take?", "knowledge_base_id": kb_id},
            headers=_auth(token),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Refunds take 5 days [1]."
    assert len(body["sources"]) == 1
    assert body["sources"][0]["score"] > 0.9


def test_chat_with_insufficient_context_returns_fallback(client):
    token = _signup_and_token(client, email="insufficient@example.com")
    kb_id = _create_kb_with_document(client, token, embedding=[1.0, 0.0, 0.0])

    with patch("app.services.rag_service.generate_embeddings", return_value=[[0.0, 1.0, 0.0]]):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "Unrelated question", "knowledge_base_id": kb_id},
            headers=_auth(token),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "enough information" in body["answer"]
    assert body["sources"] == []


def test_chat_without_knowledge_base_id_uses_plain_reply(client):
    token = _signup_and_token(client, email="plain@example.com", role="customer")
    with patch("app.services.chat_service.generate_chat_reply", return_value="Plain reply"):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "hi"},
            headers=_auth(token),
        )
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Plain reply"
    assert resp.json()["sources"] == []
