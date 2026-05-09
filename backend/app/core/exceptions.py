from __future__ import annotations

from fastapi import HTTPException


class AppError(Exception):
    status_code: int = 500
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


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


def as_http_exception(error: AppError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)
