from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 500
    detail: str = "An unexpected error occurred."
    extra: dict[str, Any]
    commit_changes: bool

    def __init__(
        self,
        detail: str | None = None,
        *,
        extra: dict[str, Any] | None = None,
        commit_changes: bool = False,
    ) -> None:
        if detail is not None:
            self.detail = detail
        self.extra = extra or {}
        self.commit_changes = commit_changes
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


class EventAuthorizationValidationError(ValidationError):
    pass


class EventAuthorizationForbiddenError(AuthorizationError):
    pass


class EventAuthorizationNotFoundError(NotFoundError):
    detail = "Event authorization not found."


class ExceptionRegistrationOfferValidationError(ValidationError):
    pass


class ExceptionRegistrationOfferForbiddenError(AuthorizationError):
    pass


class ExceptionRegistrationOfferNotFoundError(NotFoundError):
    detail = "Exception registration offer not found."


class ExceptionRegistrationOfferConflictError(ConflictError):
    pass


class ExceptionRegistrationOfferExpiredError(ExceptionRegistrationOfferConflictError):
    detail = "This exception registration offer has expired."


class RegistrationValidationError(ValidationError):
    pass


class RegistrationConflictError(ConflictError):
    pass


class RegistrationNotFoundError(NotFoundError):
    detail = "Registration not found."


class RefundRequestValidationError(ValidationError):
    pass


class RefundRequestConflictError(ConflictError):
    pass


class RefundRequestNotFoundError(NotFoundError):
    detail = "Refund request not found."


class UserNotificationNotFoundError(NotFoundError):
    detail = "User notification not found."


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


class StaffAccountNotFoundError(NotFoundError):
    detail = "Staff account not found."


class StaffNotificationNotFoundError(NotFoundError):
    detail = "Staff notification not found."


class StaffOperationValidationError(ValidationError):
    pass


class StaffOperationConflictError(ConflictError):
    pass


class StaffAccessForbiddenError(AuthorizationError):
    detail = "You do not have access to registrations for this event."


class StaffOperationForbiddenError(AuthorizationError):
    pass


class InvalidWebhookSignatureError(BadRequestError):
    detail = "Webhook signature is invalid."


class WaitlistPromotionNotFoundError(NotFoundError):
    detail = "Waitlist promotion offer not found."


class WaitlistPromotionValidationError(ValidationError):
    pass


class WaitlistPromotionConflictError(ConflictError):
    pass


class WaitlistPromotionExpiredError(WaitlistPromotionConflictError):
    detail = "This payment offer has expired."


class ManualReviewCaseValidationError(ValidationError):
    pass


class ManualReviewCaseConflictError(ConflictError):
    pass


class ManualReviewCaseForbiddenError(AuthorizationError):
    pass


class ManualReviewCaseNotFoundError(NotFoundError):
    detail = "Manual review case not found."


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
