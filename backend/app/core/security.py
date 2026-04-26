from datetime import UTC, datetime, timedelta

from app.core.config import Settings


def access_token_expiry(settings: Settings) -> timedelta:
    return timedelta(hours=settings.jwt_access_expiry_hours)


def refresh_token_expiry(settings: Settings) -> timedelta:
    return timedelta(days=settings.jwt_refresh_expiry_days)


def utc_now() -> datetime:
    return datetime.now(UTC)
