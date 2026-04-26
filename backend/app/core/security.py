from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import bcrypt
from jose import jwt

from app.core.config import Settings
from app.models.staff import StaffAccount

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def access_token_expiry(settings: Settings) -> timedelta:
    return timedelta(hours=settings.jwt_access_expiry_hours)


def refresh_token_expiry(settings: Settings) -> timedelta:
    return timedelta(days=settings.jwt_refresh_expiry_days)


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_access_token(*, account: StaffAccount, settings: Settings, expires_delta: timedelta | None = None) -> tuple[str, datetime]:
    expires_at = utc_now() + (expires_delta or access_token_expiry(settings))
    payload = {
        "sub": account.id,
        "role": account.role.value,
        "token_type": ACCESS_TOKEN_TYPE,
        "iat": int(utc_now().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires_at


def create_refresh_token(*, account: StaffAccount, settings: Settings, expires_delta: timedelta | None = None) -> tuple[str, datetime, str]:
    token_id = str(uuid4())
    expires_at = utc_now() + (expires_delta or refresh_token_expiry(settings))
    payload = {
        "sub": account.id,
        "role": account.role.value,
        "token_type": REFRESH_TOKEN_TYPE,
        "jti": token_id,
        "iat": int(utc_now().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires_at, token_id


def decode_token(token: str, settings: Settings) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
