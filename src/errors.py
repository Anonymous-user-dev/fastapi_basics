from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, status
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


class BooklyException(Exception):
    pass


class InvalidToken(BooklyException):
    pass


class RevokedToken(BooklyException):
    pass


class AccessTokenRequired(BooklyException):
    pass


class RefreshTokenRequired(BooklyException):
    pass


class UserAlreadyExists(BooklyException):
    pass


class InvalidCredentials(BooklyException):
    pass


class InsufficientPermission(BooklyException):
    pass


class BookNotFound(BooklyException):
    pass


class TagNotFound(BooklyException):
    pass


class TagAlreadyExists(BooklyException):
    pass


class UserNotFound(BooklyException):
    pass


class ReviewNotFound(BooklyException):
    pass


class AccountNotVerified(BooklyException):
    pass


class RateLimitExceeded(BooklyException):
    pass


class EmailQueueUnavailable(BooklyException):
    pass


class IdempotencyKeyConflict(BooklyException):
    pass


class PreconditionRequired(BooklyException):
    pass


class StaleBookVersion(BooklyException):
    pass


class OutboxEventNotFound(BooklyException):
    pass


def create_exception_handler(
    status_code: int, initial_detail: Any
) -> Callable[[Request, Exception], JSONResponse]:
    async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(content=initial_detail, status_code=status_code)

    return exception_handler


def register_all_errors(app: FastAPI) -> None:
    handlers = {
        UserAlreadyExists: (403, "User with email already exists", "user_exists"),
        UserNotFound: (404, "User not found", "user_not_found"),
        BookNotFound: (404, "Book not found", "book_not_found"),
        TagNotFound: (404, "Tag not found", "tag_not_found"),
        TagAlreadyExists: (403, "Tag already exists", "tag_exists"),
        ReviewNotFound: (404, "Review not found", "review_not_found"),
        InvalidCredentials: (400, "Invalid Email Or Password", "invalid_email_or_password"),
        InvalidToken: (401, "Token is invalid or expired", "invalid_token"),
        RevokedToken: (401, "Token has been revoked", "token_revoked"),
        AccessTokenRequired: (401, "Please provide a valid access token", "access_token_required"),
        RefreshTokenRequired: (403, "Please provide a valid refresh token", "refresh_token_required"),
        InsufficientPermission: (403, "Insufficient permissions", "insufficient_permissions"),
        AccountNotVerified: (403, "Account not verified", "account_not_verified"),
        RateLimitExceeded: (429, "Too many requests", "rate_limit_exceeded"),
        EmailQueueUnavailable: (
            503,
            "Email service is temporarily unavailable",
            "email_queue_unavailable",
        ),
        IdempotencyKeyConflict: (
            409,
            "Idempotency key was already used for a different request",
            "idempotency_key_conflict",
        ),
        PreconditionRequired: (
            428,
            "If-Match header is required",
            "precondition_required",
        ),
        StaleBookVersion: (
            412,
            "Book has changed since it was read",
            "stale_book_version",
        ),
        OutboxEventNotFound: (
            404,
            "Failed outbox event not found",
            "outbox_event_not_found",
        ),
    }
    for exception, (status_code, message, error_code) in handlers.items():
        app.add_exception_handler(
            exception,
            create_exception_handler(status_code, {"message": message, "error_code": error_code}),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            content={"message": "Oops! Something went wrong", "error_code": "server_error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
