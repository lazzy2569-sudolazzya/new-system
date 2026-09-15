"""RBAC dependency plus the registry that backs the CI coverage guard.

Every protected route must depend on RequirePermission. Routes that
legitimately need no permission (public endpoints, or authenticated-only
endpoints like "who am I") must be listed explicitly in PUBLIC_ROUTES.
tests/test_permission_coverage.py enumerates every route on the app and
fails if one is in neither bucket -- this is what stops the permission
matrix from silently losing coverage as new endpoints get added (plan
section 6.3).
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/users/me"),
    # FastAPI's auto-generated docs, not application endpoints.
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
}


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token"
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


class RequirePermission:
    """Route dependency and the marker the coverage test looks for.

    Usage: dependencies=[Depends(RequirePermission("inventory.view"))]
    """

    def __init__(self, code: str):
        self.code = code

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if not user.has_permission(self.code):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing permission: {self.code}"
            )
        return user
