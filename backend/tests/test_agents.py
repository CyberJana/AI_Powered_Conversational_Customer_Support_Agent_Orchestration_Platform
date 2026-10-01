"""Agent and playbook CRUD endpoint tests (Phase 8)."""


def _signup_and_token(client, email="agentadmin@example.com", role="admin"):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Agent Admin", "role": role},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": "Bearer " + token}


def test_create_agent_requires_admin(client):
    token = _signup_and_token(client, email="customer@example.com", role="customer")
    resp = client.post("/api/v1/agents", json={"name": "Support Bot"}, headers=_auth(token))
    assert resp.status_code == 403


def test_create_and_list_agents(client):
    token = _signup_and_token(client)
    create_resp = client.post(
        "/api/v1/agents",
        json={
            "name": "Support Bot",
            "description": "Handles general support",
            "system_instructions": "Be helpful and concise.",
            "confidence_threshold": 0.7,
        },
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["name"] == "Support Bot"
    assert body["confidence_threshold"] == 0.7
    assert body["allowed_tools"] == []

    list_resp = client.get("/api/v1/agents", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_create_agent_rejects_unknown_tool(client):
    token = _signup_and_token(client, email="tooladmin@example.com")
    resp = client.post(
        "/api/v1/agents",
        json={"name": "Bad Bot", "allowed_tools": ["does_not_exist"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_create_agent_rejects_unknown_knowledge_base(client):
    token = _signup_and_token(client, email="kbadmin@example.com")
    fake_kb_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post(
        "/api/v1/agents",
        json={"name": "KB Bot", "knowledge_base_ids": [fake_kb_id]},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_get_update_delete_agent(client):
    token = _signup_and_token(client, email="crudadmin@example.com")
    agent_id = client.post("/api/v1/agents", json={"name": "Bot"}, headers=_auth(token)).json()["id"]

    get_resp = client.get(f"/api/v1/agents/{agent_id}", headers=_auth(token))
    assert get_resp.status_code == 200

    update_resp = client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Renamed Bot", "confidence_threshold": 0.9},
        headers=_auth(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Renamed Bot"
    assert update_resp.json()["confidence_threshold"] == 0.9

    delete_resp = client.delete(f"/api/v1/agents/{agent_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/api/v1/agents/{agent_id}", headers=_auth(token))
    assert missing_resp.status_code == 404


def test_agents_are_scoped_per_organization(client):
    token_a = _signup_and_token(client, email="orga@example.com")
    token_b = _signup_and_token(client, email="orgb@example.com")

    agent_id = client.post("/api/v1/agents", json={"name": "Org A Bot"}, headers=_auth(token_a)).json()["id"]

    cross_org_resp = client.get(f"/api/v1/agents/{agent_id}", headers=_auth(token_b))
    assert cross_org_resp.status_code == 404

    list_resp = client.get("/api/v1/agents", headers=_auth(token_b))
    assert list_resp.json() == []


def test_create_playbook_validates_intent_and_steps(client):
    token = _signup_and_token(client, email="playbookadmin@example.com")
    agent_id = client.post("/api/v1/agents", json={"name": "Order Bot"}, headers=_auth(token)).json()["id"]

    bad_intent_resp = client.post(
        "/api/v1/playbooks",
        json={"agent_id": agent_id, "name": "Order Tracking", "intent": "not_a_real_intent", "steps": []},
        headers=_auth(token),
    )
    assert bad_intent_resp.status_code == 422

    bad_step_resp = client.post(
        "/api/v1/playbooks",
        json={
            "agent_id": agent_id,
            "name": "Order Tracking",
            "intent": "order_tracking",
            "steps": [{"type": "not_a_real_step"}],
        },
        headers=_auth(token),
    )
    assert bad_step_resp.status_code == 422

    good_resp = client.post(
        "/api/v1/playbooks",
        json={
            "agent_id": agent_id,
            "name": "Order Tracking",
            "intent": "order_tracking",
            "steps": [
                {"type": "tool_call", "config": {"tool": "lookup_order"}},
                {"type": "respond", "config": {}},
            ],
        },
        headers=_auth(token),
    )
    assert good_resp.status_code == 201
    assert good_resp.json()["intent"] == "order_tracking"
    assert len(good_resp.json()["steps"]) == 2


def test_list_playbooks_filters_by_agent_and_org(client):
    token = _signup_and_token(client, email="playbooklist@example.com")
    other_token = _signup_and_token(client, email="otherorg@example.com")

    agent_id = client.post("/api/v1/agents", json={"name": "Bot One"}, headers=_auth(token)).json()["id"]
    other_agent_id = client.post("/api/v1/agents", json={"name": "Bot Two"}, headers=_auth(token)).json()["id"]

    client.post(
        "/api/v1/playbooks",
        json={"agent_id": agent_id, "name": "PB1", "intent": "faq", "steps": []},
        headers=_auth(token),
    )
    client.post(
        "/api/v1/playbooks",
        json={"agent_id": other_agent_id, "name": "PB2", "intent": "refund", "steps": []},
        headers=_auth(token),
    )

    filtered_resp = client.get(f"/api/v1/playbooks?agent_id={agent_id}", headers=_auth(token))
    assert filtered_resp.status_code == 200
    assert len(filtered_resp.json()) == 1

    all_resp = client.get("/api/v1/playbooks", headers=_auth(token))
    assert len(all_resp.json()) == 2

    other_org_resp = client.get("/api/v1/playbooks", headers=_auth(other_token))
    assert other_org_resp.json() == []


def test_update_and_delete_playbook(client):
    token = _signup_and_token(client, email="playbookupdate@example.com")
    agent_id = client.post("/api/v1/agents", json={"name": "Bot"}, headers=_auth(token)).json()["id"]
    playbook_id = client.post(
        "/api/v1/playbooks",
        json={"agent_id": agent_id, "name": "PB", "intent": "faq", "steps": []},
        headers=_auth(token),
    ).json()["id"]

    update_resp = client.put(
        f"/api/v1/playbooks/{playbook_id}",
        json={"name": "Renamed PB"},
        headers=_auth(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Renamed PB"

    delete_resp = client.delete(f"/api/v1/playbooks/{playbook_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/api/v1/playbooks/{playbook_id}", headers=_auth(token))
    assert missing_resp.status_code == 404
