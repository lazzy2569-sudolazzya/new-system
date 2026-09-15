from app.config import settings
from app.models import Permission, Role, User
from app.security import hash_password


def _make_user(db, username, password, role_name="storekeeper", permissions=()):
    role = Role(name=role_name)
    db.add(role)
    db.flush()
    for code in permissions:
        perm = db.query(Permission).filter_by(code=code).first()
        if perm is None:
            perm = Permission(code=code)
            db.add(perm)
            db.flush()
        role.permissions.append(perm)
    user = User(
        username=username,
        full_name=username.title(),
        password_hash=hash_password(password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_login_succeeds_with_correct_password(client, db):
    _make_user(db, "alice", "correct horse battery")
    resp = client.post(
        "/api/v1/auth/login", data={"username": "alice", "password": "correct horse battery"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_fails_with_wrong_password(client, db):
    _make_user(db, "bob", "correct horse battery")
    resp = client.post("/api/v1/auth/login", data={"username": "bob", "password": "wrong"})
    assert resp.status_code == 401


def test_account_locks_after_repeated_failures(client, db):
    _make_user(db, "carol", "correct horse battery")
    for _ in range(settings.login_lockout_threshold):
        client.post("/api/v1/auth/login", data={"username": "carol", "password": "wrong"})

    resp = client.post(
        "/api/v1/auth/login", data={"username": "carol", "password": "correct horse battery"}
    )
    assert resp.status_code == 423


def test_storekeeper_without_permission_is_denied(client, db):
    _make_user(db, "dave", "correct horse battery", role_name="storekeeper", permissions=())
    login = client.post(
        "/api/v1/auth/login", data={"username": "dave", "password": "correct horse battery"}
    )
    token = login.json()["access_token"]

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_storekeeper_response_has_no_contact_fields(client, db):
    _make_user(
        db, "erin", "correct horse battery", role_name="storekeeper", permissions=["users.view"]
    )
    login = client.post(
        "/api/v1/auth/login", data={"username": "erin", "password": "correct horse battery"}
    )
    token = login.json()["access_token"]

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.text
    for forbidden in ("email", "phone"):
        assert forbidden not in body, f"{forbidden} leaked to a role without users.view_contact"
