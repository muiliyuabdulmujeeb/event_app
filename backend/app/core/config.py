from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")
    test_database_url: str = Field(..., alias="TEST_DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_access_expiry_hours: int = Field(1, alias="JWT_ACCESS_EXPIRY_HOURS")
    jwt_refresh_expiry_days: int = Field(7, alias="JWT_REFRESH_EXPIRY_DAYS")
    active_payment_gateway: str = Field("mock", alias="ACTIVE_PAYMENT_GATEWAY")
    paystack_secret_key: str = Field("", alias="PAYSTACK_SECRET_KEY")
    squad_secret_key: str = Field("", alias="SQUAD_SECRET_KEY")
    mock_payment_base_url: str = Field("http://localhost:8000", alias="MOCK_PAYMENT_BASE_URL")
    paystack_api_base_url: str = Field("https://api.paystack.co", alias="PAYSTACK_API_BASE_URL")
    squad_api_base_url: str = Field("", alias="SQUAD_API_BASE_URL")
    payment_callback_url: str = Field("", alias="PAYMENT_CALLBACK_URL")
    paystack_checkout_base_url: str = Field("https://checkout.paystack.com", alias="PAYSTACK_CHECKOUT_BASE_URL")
    squad_checkout_base_url: str = Field("https://checkout.squadco.com", alias="SQUAD_CHECKOUT_BASE_URL")
    payment_timeout_minutes: int = Field(30, alias="PAYMENT_TIMEOUT_MINUTES")
    email_provider: str = Field("console", alias="EMAIL_PROVIDER")
    email_api_key: str = Field("", alias="EMAIL_API_KEY")
    email_from: str = Field("noreply@eventapp.local", alias="EMAIL_FROM")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def ensure_runtime_directories(self) -> None:
        Path("alembic/versions").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
