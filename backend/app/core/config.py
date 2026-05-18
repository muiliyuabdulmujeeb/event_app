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
    application_base_url: str = Field("http://localhost:8000", alias="APPLICATION_BASE_URL")
    waitlist_promotion_default_expiry_minutes: int = Field(30, alias="WAITLIST_PROMOTION_DEFAULT_EXPIRY_MINUTES")
    email_provider: str = Field("console", alias="EMAIL_PROVIDER")
    email_api_key: str = Field("", alias="EMAIL_API_KEY")
    email_from: str = Field("noreply@eventapp.local", alias="EMAIL_FROM")
    email_from_name: str = Field("Event Management", alias="EMAIL_FROM_NAME")
    resend_api_key: str = Field("", alias="RESEND_API_KEY")
    resend_api_base_url: str = Field("https://api.resend.com", alias="RESEND_API_BASE_URL")
    sendgrid_api_key: str = Field("", alias="SENDGRID_API_KEY")
    sendgrid_api_base_url: str = Field("https://api.sendgrid.com", alias="SENDGRID_API_BASE_URL")
    mailgun_api_key: str = Field("", alias="MAILGUN_API_KEY")
    mailgun_domain: str = Field("", alias="MAILGUN_DOMAIN")
    mailgun_api_base_url: str = Field("https://api.mailgun.net", alias="MAILGUN_API_BASE_URL")
    zoho_mail_access_token: str = Field("", alias="ZOHO_MAIL_ACCESS_TOKEN")
    zoho_mail_account_id: str = Field("", alias="ZOHO_MAIL_ACCOUNT_ID")
    zoho_mail_api_base_url: str = Field("https://mail.zoho.com", alias="ZOHO_MAIL_API_BASE_URL")
    aws_ses_region: str = Field("", alias="AWS_SES_REGION")
    aws_ses_access_key_id: str = Field("", alias="AWS_SES_ACCESS_KEY_ID")
    aws_ses_secret_access_key: str = Field("", alias="AWS_SES_SECRET_ACCESS_KEY")
    aws_ses_session_token: str = Field("", alias="AWS_SES_SESSION_TOKEN")
    aws_ses_endpoint_url: str = Field("", alias="AWS_SES_ENDPOINT_URL")

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
