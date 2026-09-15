from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    username: str
    full_name: str
    role: str


class UserWithContact(UserPublic):
    """Superset of UserPublic, never the other way around.

    Plan section 3.4: a new sensitive field must be explicitly added to the
    privileged schema to become visible anywhere. A single schema with
    optional fields fails open (a new column defaults to visible); separate
    classes fail closed.
    """

    email: str | None = None
    phone: str | None = None


# Selected server-side by the caller's permissions -- see routers/users.py.
# Keyed by the permission that unlocks the richer schema; the endpoint picks
# the first match and falls back to UserPublic.
RESPONSE_SCHEMA_BY_PERMISSION: dict[str, type[UserPublic]] = {
    "users.view_contact": UserWithContact,
}
DEFAULT_USER_SCHEMA: type[UserPublic] = UserPublic
