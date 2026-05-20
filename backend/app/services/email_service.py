from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError, EmailMessageValidationError
from app.core.security import utc_now
from app.schemas.email import EmailMessage
from app.services.email_providers import EmailSendResult, build_email_provider


REAL_EMAIL_PROVIDERS = frozenset({"resend", "zoho_mail", "sendgrid", "mailgun", "amazon_ses"})
SPECIAL_EMAIL_PROVIDERS = frozenset({"console", "mock"})
EMAIL_PROVIDER_ALIASES = {
    "ses": "amazon_ses",
    "zoho": "zoho_mail",
}


@dataclass(frozen=True)
class EmailSendExecutionResult:
    success: bool
    send_result: EmailSendResult | None
    provider_attempts: list[dict[str, Any]]
    total_allowed_attempts: int
    should_retry: bool
    error_class: str | None = None
    error_message: str | None = None
    failure_category: str | None = None


@dataclass
class EmailService:
    settings: Settings

    async def send_message(
        self,
        message: EmailMessage,
        *,
        previous_attempts: list[dict[str, Any]] | None = None,
    ) -> EmailSendExecutionResult:
        attempts = list(previous_attempts or [])
        provider_sequence = self._resolve_provider_attempt_sequence()
        current_attempt_index = len(attempts)
        if current_attempt_index >= len(provider_sequence):
            raise EmailConfigurationError("Email provider attempt sequence is exhausted.")

        provider_name = provider_sequence[current_attempt_index]
        provider_attempt_number = sum(1 for attempt in attempts if attempt["provider"] == provider_name) + 1

        try:
            send_result = await build_email_provider(self.settings, provider_name=provider_name).send(message)
        except Exception as exc:
            should_retry = len(attempts) + 1 < len(provider_sequence) and self._is_retryable_failure(exc)
            attempts.append(
                self._build_provider_attempt(
                    provider=provider_name,
                    provider_attempt=provider_attempt_number,
                    success=False,
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            return EmailSendExecutionResult(
                success=False,
                send_result=None,
                provider_attempts=attempts,
                total_allowed_attempts=len(provider_sequence),
                should_retry=should_retry,
                error_class=type(exc).__name__,
                error_message=str(exc),
                failure_category=self._resolve_failure_category(exc),
            )

        attempts.append(
            self._build_provider_attempt(
                provider=provider_name,
                provider_attempt=provider_attempt_number,
                success=True,
            )
        )
        return EmailSendExecutionResult(
            success=True,
            send_result=send_result,
            provider_attempts=attempts,
            total_allowed_attempts=len(provider_sequence),
            should_retry=False,
        )

    def enqueue_message(self, message: EmailMessage) -> None:
        from app.workers.email_tasks import send_email_task

        send_email_task.delay(message.model_dump(mode="json"))

    def enqueue_messages(self, messages: list[EmailMessage]) -> None:
        for message in messages:
            self.enqueue_message(message)

    def _resolve_provider_attempt_sequence(self) -> list[str]:
        active_provider = self._normalize_provider_name(self.settings.email_provider)
        if active_provider in SPECIAL_EMAIL_PROVIDERS:
            return [active_provider]

        provider_chain = [
            self._normalize_provider_name(provider_name)
            for provider_name in self.settings.email_provider_failover_chain.split(",")
            if provider_name.strip()
        ]
        if not provider_chain:
            provider_chain = [active_provider]

        available_chain = [
            provider_name
            for provider_name in provider_chain
            if provider_name in REAL_EMAIL_PROVIDERS and self._is_provider_available(provider_name)
        ]
        if not available_chain:
            raise EmailConfigurationError("No configured real email providers are available for failover.")

        return [
            provider_name
            for provider_name in available_chain
            for _ in range(self.settings.email_provider_attempts_per_provider)
        ]

    def _normalize_provider_name(self, provider_name: str) -> str:
        normalized = provider_name.strip().lower()
        return EMAIL_PROVIDER_ALIASES.get(normalized, normalized)

    def _is_provider_available(self, provider_name: str) -> bool:
        if provider_name == "resend":
            return bool(self.settings.resend_api_key)
        if provider_name == "zoho_mail":
            return bool(self.settings.zoho_mail_access_token and self.settings.zoho_mail_account_id)
        if provider_name == "sendgrid":
            return bool(self.settings.sendgrid_api_key)
        if provider_name == "mailgun":
            return bool(self.settings.mailgun_api_key and self.settings.mailgun_domain)
        if provider_name == "amazon_ses":
            return bool(self.settings.aws_ses_region)
        return False

    def _build_provider_attempt(
        self,
        *,
        provider: str,
        provider_attempt: int,
        success: bool,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "provider": provider,
            "provider_attempt": provider_attempt,
            "success": success,
            "error_class": error_class,
            "error_message": error_message,
            "attempted_at": utc_now().isoformat(),
        }

    def _resolve_failure_category(self, exc: Exception) -> str:
        if isinstance(exc, EmailMessageValidationError):
            return "message_validation"
        if isinstance(exc, EmailConfigurationError):
            return "configuration_failure"
        return "delivery_failure"

    def _is_retryable_failure(self, exc: Exception) -> bool:
        return not isinstance(exc, EmailMessageValidationError)
