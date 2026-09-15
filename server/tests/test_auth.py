from app.config import settings


def test_login_succeeds_with_correct_password(client, make_user):
    make_user("alice", "correct horse battery")
    resp = client.post(
        "/api/v1/auth/login", data={"username": "alice", "password": "correct horse battery"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_fails_with_wrong_password(client, make_user):
    make_user("bob", "correct horse battery")
    resp = client.post("/api/v1/auth/login", data={"username": "bob", "password": "wrong"})
    assert resp.status_code == 401


def test_account_locks_after_repeated_failures(client, make_user):
    make_user("carol", "correct horse battery")
    for _ in range(settings.login_lockout_threshold):
        client.post("/api/v1/auth/login", data={"username": "carol", "password": "wrong"})

    resp = client.post(
        "/api/v1/auth/login", data={"username": "carol", "password": "correct horse battery"}
    )
    assert resp.status_code == 423


def test_storekeeper_without_permission_is_denied(client, make_user, login_as):
    make_user("dave", "correct horse battery", role_name="storekeeper", permissions=())
    token = login_as("dave", "correct horse battery")

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_storekeeper_response_has_no_contact_fields(client, make_user, login_as):
    make_user("erin", "correct horse battery", role_name="storekeeper", permissions=["users.view"])
    token = login_as("erin", "correct horse battery")

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.text
    for forbidden in ("email", "phone"):
        assert forbidden not in body, f"{forbidden} leaked to a role without users.view_contact"
