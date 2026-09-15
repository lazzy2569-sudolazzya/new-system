import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models import Permission, Role, User
from app.security import hash_password

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://erp:erp@localhost:5432/erp_test"
)

SERVER_DIR = Path(__file__).resolve().parents[1]

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _run_alembic(*args: str) -> None:
    # A real subprocess, not the in-process alembic API: app.config.settings
    # is instantiated once at import time from DATABASE_URL, so pointing a
    # single already-imported process at a different database mid-run isn't
    # reliable. A fresh subprocess with DATABASE_URL overridden reads it
    # correctly every time.
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=SERVER_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
        capture_output=True,
        text=True,
    )


def _reset_schema() -> None:
    # Not alembic downgrade for cleanup: a down-migration correctly refuses
    # to delete a seeded role that a test's own data still references via
    # FK (that's the right behavior in production), which makes it the
    # wrong tool for "make the test database empty again" -- it would leave
    # the next test colliding with this test's leftovers. Dropping the
    # whole schema sidesteps FK ordering entirely.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture()
def db():
    # Migrated for real, not built from Base.metadata.create_all(). That
    # matters: create_all() only knows about columns/FKs/indexes declared
    # on the ORM models -- it silently skips migration-only raw SQL like
    # the stock_movements append-only RULE and the audit triggers, which
    # are exactly the protections plan section 3.1 depends on. A schema
    # built by create_all() would pass every test while those protections
    # were completely absent.
    _reset_schema()
    _run_alembic("upgrade", "head")
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db):
    def _make(username, password, role_name="storekeeper", permissions=()):
        role = db.query(Role).filter_by(name=role_name).first()
        if role is None:
            role = Role(name=role_name)
            db.add(role)
            db.flush()
        for code in permissions:
            perm = db.query(Permission).filter_by(code=code).first()
            if perm is None:
                perm = Permission(code=code)
                db.add(perm)
                db.flush()
            if perm not in role.permissions:
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

    return _make


@pytest.fixture()
def login_as(client):
    def _login(username, password):
        resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
        resp.raise_for_status()
        return resp.json()["access_token"]

    return _login
