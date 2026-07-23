"""SQLite-backed user store with at-rest encryption for API keys.

Each user owns their own API keys (Groq, Gemini, YouTube) and pipeline
preferences. Keys are encrypted with Fernet before being written to the
database; the Fernet key comes from AUTOCLIPPER_SECRET (env). If that secret
is not set we derive a per-process key and warn (keys are still obfuscated,
but not securely persisted across restarts).
"""
import base64
import os
import hashlib
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Field, Session, SQLModel, create_engine, select

from . import config

# --- Encryption ----------------------------------------------------------
def _fernet_key() -> bytes:
    """Derive a Fernet key from AUTOCLIPPER_SECRET (or generate an ephemeral one)."""
    secret = os.environ.get("AUTOCLIPPER_SECRET")
    if secret:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)
    return Fernet.generate_key()


_fernet = Fernet(_fernet_key())


def encrypt_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None


# --- Engine --------------------------------------------------------------
DB_PATH = os.environ.get(
    "AUTOCLIPPER_DB",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "autoclipper.db")),
)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create tables. Idempotent; safe to call on startup."""
    SQLModel.metadata.create_all(engine)
    # Migrate: add facebook_token column if missing (for existing DBs)
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN facebook_token TEXT")
            conn.commit()
        except Exception:
            pass  # column already exists


def get_session():
    with Session(engine) as session:
        yield session


# --- Models --------------------------------------------------------------
class User(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    groq_key: str | None = None
    gemini_key: str | None = None
    youtube_api_key: str | None = None
    gemini_model: str | None = None
    whisper_model: str | None = None
    youtube_cookies: str | None = None
    youtube_token: str | None = None  # encrypted JSON of the OAuth credentials
    facebook_token: str | None = None  # encrypted JSON of Facebook OAuth token
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserCreate(SQLModel):
    username: str
    password: str


class UserLogin(SQLModel):
    username: str
    password: str


class UserSettings(SQLModel):
    """Settings the user can read/update (keys are returned decrypted)."""
    groq_key: str | None = None
    gemini_key: str | None = None
    youtube_api_key: str | None = None
    gemini_model: str | None = None
    whisper_model: str | None = None
    youtube_cookies: str | None = None


class UserSettingsUpdate(SQLModel):
    model_config = {"populate_by_name": True}

    groq_key: str | None = None
    gemini_key: str | None = None
    youtube_api_key: str | None = None
    gemini_model: str | None = None
    whisper_model: str | None = None
    youtube_cookies: str | None = None


class UserPublic(SQLModel):
    id: int
    username: str
    created_at: datetime


# --- Helpers -------------------------------------------------------------
def get_user_by_username(session: Session, username: str) -> Optional[User]:
    return session.exec(select(User).where(User.username == username)).first()


def create_user(session: Session, data: UserCreate, password_hash: str) -> User:
    user = User(username=data.username, password_hash=password_hash)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def settings_for(user: User) -> UserSettings:
    """Return the user's settings with keys decrypted for display."""
    return UserSettings(
        groq_key=decrypt_value(user.groq_key),
        gemini_key=decrypt_value(user.gemini_key),
        youtube_api_key=decrypt_value(user.youtube_api_key),
        gemini_model=user.gemini_model,
        whisper_model=user.whisper_model,
        youtube_cookies=decrypt_value(user.youtube_cookies),
    )


def apply_settings(user: User, data: UserSettingsUpdate) -> None:
    """Persist settings, encrypting any key fields that were provided."""
    if data.groq_key is not None:
        user.groq_key = encrypt_value(data.groq_key)
    if data.gemini_key is not None:
        user.gemini_key = encrypt_value(data.gemini_key)
    if data.youtube_api_key is not None:
        user.youtube_api_key = encrypt_value(data.youtube_api_key)
    if data.gemini_model is not None:
        user.gemini_model = data.gemini_model
    if data.whisper_model is not None:
        user.whisper_model = data.whisper_model
    if data.youtube_cookies is not None:
        user.youtube_cookies = encrypt_value(data.youtube_cookies)


def save_youtube_token(user: User, token_json: str) -> None:
    """Encrypt and store the user's YouTube OAuth token (JSON string)."""
    user.youtube_token = encrypt_value(token_json)


def load_youtube_token(user: User) -> Optional[str]:
    """Return the user's YouTube OAuth token JSON, decrypted (or None)."""
    return decrypt_value(user.youtube_token)


def save_facebook_token(user: User, token_data: dict) -> None:
    """Encrypt and store the user's Facebook OAuth token (dict serialized to JSON)."""
    import json
    user.facebook_token = encrypt_value(json.dumps(token_data))


def load_facebook_token(user: User) -> Optional[dict]:
    """Return the user's Facebook OAuth token dict, decrypted (or None)."""
    import json
    raw = decrypt_value(user.facebook_token)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
