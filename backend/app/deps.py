from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token, role_at_least

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _user_from_token(token: str, db: Session) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or not user.is_active:
        return None
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    user = _user_from_token(token, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return user


def require_role(required: str):
    """Dependency factory. Server-side enforcement, not just a UI hint."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if not role_at_least(user.role, required):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"needs '{required}' role or higher"
            )
        return user

    return _checker


def user_from_token_str(token: str, db: Session) -> User | None:
    # used by the websocket handshake, which can't use the request dependency
    return _user_from_token(token, db)
