"""Knowledge base and document ingestion endpoint tests."""
from unittest.mock import patch


def _signup_and_token(client, email="kbuser@example.com", role="admin"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "KB User", "role": role},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_knowledge_base_requires_admin(client):
    token = _signup_and_token(client, email="customer@example.com", role="customer")
    resp = client.post("/api/v1/knowledge-bases", json={"name": "Docs"}, headers=_auth(token))
    assert resp.status_code == 403


def test_create_and_list_knowledge_bases(client):
    token = _signup_and_token(client)
    create_resp = client.post(
        "/api/v1/knowledge-bases", json={"name": "Product Docs", "description": "FAQ"}, headers=_auth(token)
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["name"] == "Product Docs"

    list_resp = client.get("/api/v1/knowledge-bases", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_upload_document_without_openai_key_marks_failed(client):
    token = _signup_and_token(client, email="noembed@example.com")
    kb_id = client.post("/api/v1/knowledge-bases", json={"name": "KB"}, headers=_auth(token)).json()["id"]

    resp = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("policy.txt", b"Refunds are processed within 5 business days.", "text/plain")},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "FAILED"
    assert "OPENAI_API_KEY" in body["error_message"]


def test_upload_document_with_mocked_embeddings_completes_and_lists(client):
    token = _signup_and_token(client, email="embed@example.com")
    kb_id = client.post("/api/v1/knowledge-bases", json={"name": "KB"}, headers=_auth(token)).json()["id"]

    with patch("app.services.ingestion_service.generate_embeddings", return_value=[[0.1, 0.2, 0.3]]):
        resp = client.post(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            files={"file": ("policy.txt", b"Refunds are processed within 5 business days.", "text/plain")},
            headers=_auth(token),
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "COMPLETED"

    list_resp = client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_upload_document_rejects_unsupported_file_type(client):
    token = _signup_and_token(client, email="badfile@example.com")
    kb_id = client.post("/api/v1/knowledge-bases", json={"name": "KB"}, headers=_auth(token)).json()["id"]

    resp = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("image.png", b"binarydata", "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_reindex_and_delete_document(client):
    token = _signup_and_token(client, email="reindex@example.com")
    kb_id = client.post("/api/v1/knowledge-bases", json={"name": "KB"}, headers=_auth(token)).json()["id"]

    with patch("app.services.ingestion_service.generate_embeddings", return_value=[[0.1, 0.2, 0.3]]):
        doc = client.post(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            files={"file": ("policy.txt", b"Refunds within 5 days.", "text/plain")},
            headers=_auth(token),
        ).json()

        reindex_resp = client.post(f"/api/v1/documents/{doc['id']}/reindex", headers=_auth(token))
    assert reindex_resp.status_code == 200
    assert reindex_resp.json()["status"] == "COMPLETED"

    delete_resp = client.delete(f"/api/v1/documents/{doc['id']}", headers=_auth(token))
    assert delete_resp.status_code == 204
