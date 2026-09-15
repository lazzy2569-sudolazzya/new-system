from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import RequirePermission, get_current_user
from app.schemas import (
    DEFAULT_USER_SCHEMA,
    RESPONSE_SCHEMA_BY_PERMISSION,
    UserPublic,
    UserWithContact,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(id=user.id, username=user.username, full_name=user.full_name, role=user.role.name)


@router.get(
    "",
    response_model=None,
    dependencies=[Depends(RequirePermission("users.view"))],
)
def list_users(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[UserPublic]:
    # Schema picked server-side by the caller's permissions, never by a
    # query param or by hiding fields client-side (plan section 3.4).
    schema = DEFAULT_USER_SCHEMA
    for permission, candidate in RESPONSE_SCHEMA_BY_PERMISSION.items():
        if user.has_permission(permission):
            schema = candidate
            break

    rows = db.query(User).all()
    if schema is UserWithContact:
        return [
            UserWithContact(
                id=r.id, username=r.username, full_name=r.full_name,
                role=r.role.name, email=r.email, phone=r.phone,
            )
            for r in rows
        ]
    return [
        UserPublic(id=r.id, username=r.username, full_name=r.full_name, role=r.role.name)
        for r in rows
    ]
