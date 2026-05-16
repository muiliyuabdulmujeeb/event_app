from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 500
    detail: str = "An unexpected error occurred."
    extra: dict[str, Any]

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None) -> None:
        if detail is not None:
            self.detail = detail
        self.extra = extra or {}
        super().__init__(self.detail)

    def to_payload(self) -> dict[str, Any]:
        return {"detail": self.detail, **self.extra}


class AuthenticationError(AppError):
    status_code = 401


class AuthorizationError(AppError):
    status_code = 403


class ValidationError(AppError):
    status_code = 422


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class BadGatewayError(AppError):
    status_code = 502


class BadRequestError(AppError):
    status_code = 400


class InvalidCredentialsError(AuthenticationError):
    detail = "Invalid email or password."


class InvalidRefreshTokenError(AuthenticationError):
    detail = "Refresh token is invalid or has expired. Please log in again."


class AccountDisabledError(AuthorizationError):
    detail = "This account has been disabled."


class EventNotFoundError(NotFoundError):
    detail = "Event not found."


class EventValidationError(ValidationError):
    pass


class EventConflictError(ConflictError):
    pass


class RegistrationValidationError(ValidationError):
    pass


class RegistrationConflictError(ConflictError):
    pass


class PaymentConfigurationError(AppError):
    detail = "Payment gateway configuration is invalid."


class PaymentGatewayError(BadGatewayError):
    detail = "Payment gateway initialization failed."


class EmailConfigurationError(AppError):
    detail = "Email provider configuration is invalid."


class EmailDeliveryError(BadGatewayError):
    detail = "Email delivery failed."


class PaymentNotFoundError(NotFoundError):
    detail = "Payment not found."


class InvalidWebhookSignatureError(BadRequestError):
    detail = "Webhook signature is invalid."


class DuplicateRegistrationError(RegistrationConflictError):
    def __init__(self, detail: str = "This email has already been used to register for this event.") -> None:
        super().__init__(detail, extra={"duplicate_email": True})


class DuplicateBatchSubmissionError(RegistrationValidationError):
    def __init__(self, duplicate_emails: list[str]) -> None:
        super().__init__(
            "Duplicate emails found within this batch. Each participant must have a unique email address.",
            extra={"duplicate_emails": duplicate_emails},
        )


class DuplicateBatchExistingRegistrationError(RegistrationConflictError):
    def __init__(self, duplicate_emails: list[str]) -> None:
        super().__init__(
            "One or more participants are already registered for this event. Re-submit with acknowledge_duplicates: true to proceed.",
            extra={"duplicate_emails": duplicate_emails, "duplicate_warning": True},
        )


def as_http_exception(error: AppError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def error_response(error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error.to_payload())
