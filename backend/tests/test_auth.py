"""Auth endpoint tests (signup, login, refresh, me) against SQLite."""


def _signup(client, email="user@example.com", password="Password123!", role="customer"):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": "Test User", "role": role},
    )


def test_signup_creates_user_and_returns_tokens(client):
    resp = _signup(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "user@example.com"
    assert body["role"] == "customer"
    assert body["access_token"] and body["refresh_token"]


def test_signup_duplicate_email_rejected(client):
    _signup(client)
    resp = _signup(client)
    assert resp.status_code == 409


def test_login_success(client):
    _signup(client, email="login@example.com", password="Password123!")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "Password123!"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password_rejected(client):
    _signup(client, email="wrong@example.com", password="Password123!")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "wrong@example.com", "password": "nope12345"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    signup_resp = _signup(client, email="me@example.com")
    token = signup_resp.json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


def test_refresh_returns_new_tokens(client):
    signup_resp = _signup(client, email="refresh@example.com")
    refresh_token = signup_resp.json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_access_token(client):
    signup_resp = _signup(client, email="badrefresh@example.com")
    access_token = signup_resp.json()["access_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
