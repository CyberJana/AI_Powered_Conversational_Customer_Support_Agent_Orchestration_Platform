"""Intent classification tests: classification persistence and no-key behavior."""
from unittest.mock import patch


def _signup_and_token(client, email="intentuser@example.com"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Intent User", "role": "customer"},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def test_chat_persists_classified_intent_on_message_and_conversation(client):
    token = _signup_and_token(client, email="classified@example.com")
    with (
        patch("app.services.intent_service.classify", return_value=("order_tracking", 0.87)),
        patch("app.services.chat_service.generate_chat_reply", return_value="Your order is on the way."),
    ):
        resp = client.post(
            "/api/v1/chat",
            json={"conversation_id": None, "message": "Where is my order?"},
            headers=_auth(token),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "order_tracking"
    conversation_id = body["conversation_id"]

    detail = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth(token))
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["intent"] == "order_tracking"
    customer_message = next(m for m in detail_body["messages"] if m["sender"] == "customer")
    assert customer_message["intent"] == "order_tracking"
    assert customer_message["intent_confidence"] == 0.87


def test_classify_intent_falls_back_to_unknown_for_unrecognized_label():
    """Unit test of llm_service.classify_intent's own safeguard: if the model
    returns a label outside the allowed taxonomy, fall back to ("unknown", 0.0)
    rather than trusting an out-of-taxonomy classification.
    """
    from unittest.mock import MagicMock

    from app.services import llm_service

    fake_message = MagicMock()
    fake_message.content = '{"intent": "not_a_real_intent", "confidence": 0.9}'
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=fake_message)]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_service, "_client", return_value=fake_client):
        intent, confidence = llm_service.classify_intent("gibberish", ["faq", "unknown"])

    assert intent == "unknown"
    assert confidence == 0.0


def test_chat_returns_503_when_intent_classification_has_no_key(client):
    token = _signup_and_token(client, email="nokey@example.com")
    resp = client.post(
        "/api/v1/chat",
        json={"conversation_id": None, "message": "hello"},
        headers=_auth(token),
    )
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]
