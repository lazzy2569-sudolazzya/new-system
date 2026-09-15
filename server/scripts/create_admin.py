"""One-off CLI to create the first admin user, after running migrations.

    python -m scripts.create_admin <username> "<full name>"

Prompts for the password interactively so it never lands in shell history.
"""
import getpass
import sys

from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password


def main() -> None:
    if len(sys.argv) != 3:
        print('usage: python -m scripts.create_admin <username> "<full name>"')
        raise SystemExit(1)
    username, full_name = sys.argv[1], sys.argv[2]

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords did not match")
        raise SystemExit(1)

    db = SessionLocal()
    try:
        role = db.query(Role).filter_by(name="admin").first()
        if role is None:
            print("admin role not found -- run `alembic upgrade head` first")
            raise SystemExit(1)
        db.add(
            User(
                username=username,
                full_name=full_name,
                password_hash=hash_password(password),
                role_id=role.id,
                is_active=True,
            )
        )
        db.commit()
        print(f"Created admin user '{username}'")
    finally:
        db.close()


if __name__ == "__main__":
    main()
