"""Authentication: password hashing, JWT issuance, and FastAPI dependencies.

Tokens are signed JWTs (HS256) using AUTOCLIPPER_JWT_SECRET (env). The
get_current_user dependency is used to protect endpoints and to resolve the
calling user's stored API keys when the request body does not supply them.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session

from .db import User, UserPublic, get_session

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("AUTOCLIPPER_TOKEN_MINUTES", "1440"))

JWT_SECRET = os.environ.get("AUTOCLIPPER_JWT_SECRET") or os.environ.get(
    "AUTOCLIPPER_SECRET", "change-me-in-production"
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the authenticated user from the bearer token, or 401."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    username = decode_token(token)
    if not username:
        raise credentials_exc
    user = (
        session.query(User).filter(User.username == username).first()
    )
    if not user:
        raise credentials_exc
    return user


def public_user(user: User) -> UserPublic:
    return UserPublic(id=user.id, username=user.username, created_at=user.created_at)
