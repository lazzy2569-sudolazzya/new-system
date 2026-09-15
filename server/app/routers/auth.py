import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import Token
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.query(User).filter(User.username == form.username).first()

    if user is not None and user.locked_until is not None:
        if user.locked_until > dt.datetime.now(dt.timezone.utc):
            raise HTTPException(
                status.HTTP_423_LOCKED,
                "Account temporarily locked due to repeated failed logins",
            )

    if user is None or not user.is_active or not verify_password(
        form.password, user.password_hash
    ):
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.login_lockout_threshold:
                user.locked_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                    minutes=settings.login_lockout_minutes
                )
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    token = create_access_token(user.id, user.username)
    return Token(access_token=token)
